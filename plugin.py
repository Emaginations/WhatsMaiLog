"""
日志小窥：让麦麦能窥见自己的log，并提供LLM总结

2026-06-14 try1: 实现日志查询、LLM总结、WebUI配置、触发词自定义
2026-06-14 try2: 添加俄语多语言支持
2026-06-14 try3: 修正 LLM Provider 的 manifest 声明与 @LLMProvider 匹配
2026-06-14 try4: 同步 client_type 为 1m.whatsmailog.provider，添加插件加载日志
2026-06-14 try5: 修正 CommandHandler 导入路径（从 maibot_sdk.types 导入）
2026-06-14 try6: 修正为正确的 Command 组件（从 maibot_sdk 导入 Command）
2026-06-14 try7: 添加 /whatsmailog（仅WebUI）和 /llmtest 测试命令
2026-06-14 try8: 修正配置模型继承 PluginConfigBase，修复 WebUI 无法加载配置的问题
2026-07-10 try9: 重构项目，参考Nightmare项目优化代码结构、完善错误处理、添加英文多语言支持
2026-07-11 try10: 修改WebUI限制逻辑：只有/xx形式命令受webui_only_commands限制，触发词不受影响
2026-07-11 try11: 修复触发词配置无效问题（动态读取config.trigger_phrases）+ 修复获取日志非最新问题
2026-07-11 try12: 添加"查你后台"功能 - 提取Maisaka后台推理输出，不经过LLM总结直接发送至聊天流
2026-07-11 try13: 修复list越界错误；查你后台仅提取"Maisaka 返回"纯文本；删除maisaka_keywords的WebUI配置
"""

from maibot_sdk import Field, MaiBotPlugin, LLMProvider, LLMProviderBase, Command, PluginConfigBase
from typing import ClassVar, List, Any, Dict, Optional
from datetime import datetime, timedelta
import aiohttp
import json
import os
import re

# ============================================================================
# 多语言化支持（中文、英文、俄语）
# ============================================================================
def _schema_i18n(
    *,
    label_en: str,
    label_ru: str,
    label_ja: Optional[str] = None,
    hint_en: Optional[str] = None,
    hint_ru: Optional[str] = None,
    hint_ja: Optional[str] = None,
    placeholder_en: Optional[str] = None,
    placeholder_ru: Optional[str] = None,
    placeholder_ja: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    """构造 WebUI 配置项多语言说明，支持英文、俄语、日语。"""
    i18n: Dict[str, Dict[str, str]] = {
        "en_US": {"label": label_en},
        "ru_RU": {"label": label_ru},
    }
    if label_ja:
        i18n["ja_JP"] = {"label": label_ja}
    if hint_en:
        i18n["en_US"]["hint"] = hint_en
    if hint_ru:
        i18n["ru_RU"]["hint"] = hint_ru
    if hint_ja:
        i18n["ja_JP"]["hint"] = hint_ja
    if placeholder_en:
        i18n["en_US"]["placeholder"] = placeholder_en
    if placeholder_ru:
        i18n["ru_RU"]["placeholder"] = placeholder_ru
    if placeholder_ja:
        i18n["ja_JP"]["placeholder"] = placeholder_ja
    return i18n

# ============================================================================
# WebUI 配置定义（均继承 PluginConfigBase）
# ============================================================================
class LogWatcherPluginConfig(PluginConfigBase):
    """插件基本配置"""
    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(
        default=True,
        description="是否启用日志小窥插件",
        json_schema_extra={
            "label": "开关",
            "i18n": _schema_i18n(label_en="Enable", label_ru="Включить"),
            "order": 0
        }
    )
    config_version: str = Field(
        default="2.0.0",
        description="配置版本",
        json_schema_extra={
            "label": "配置版本",
            "i18n": _schema_i18n(
                label_en="Config version",
                label_ru="Версия конфигурации",
                hint_en="Configuration version number.",
                hint_ru="Номер версии конфигурации."
            ),
            "order": 1
        }
    )
    trigger_phrases: List[str] = Field(
        default=["发生什么了{bot_name}", "是不是哪里出问题了"],
        description="触发关键词列表，可使用{bot_name}占位符",
        json_schema_extra={
            "label": "触发词",
            "hint": "用户发送这些消息时触发插件，可使用{bot_name}占位符",
            "i18n": _schema_i18n(
                label_en="Trigger phrases",
                label_ru="Ключевые слова",
                hint_en="Messages that trigger the plugin. Use {bot_name} as placeholder.",
                hint_ru="Сообщения, при которых плагин срабатывает. Используйте {bot_name} как плейсхолдер."
            ),
            "order": 2
        }
    )
    log_minutes: int = Field(
        default=10, ge=1, le=120,
        description="查询日志的时间范围（分钟）",
        json_schema_extra={
            "label": "查询范围（分钟）",
            "hint": "获取多久之前的日志",
            "i18n": _schema_i18n(
                label_en="Query range (minutes)",
                label_ru="Диапазон запроса (минуты)"
            ),
            "order": 3
        }
    )
    max_log_lines: int = Field(
        default=50, ge=10, le=500,
        description="最多获取的日志行数",
        json_schema_extra={
            "label": "最大日志行数",
            "hint": "最多获取的日志行数",
            "i18n": _schema_i18n(
                label_en="Max log lines",
                label_ru="Максимальное количество строк журнала"
            ),
            "order": 4
        }
    )
    log_file_path: str = Field(
        default="logs/maibot.log",
        description="日志文件路径（相对或绝对路径）",
        json_schema_extra={
            "label": "日志文件路径",
            "placeholder": "logs/maibot.log",
            "i18n": _schema_i18n(
                label_en="Log file path",
                label_ru="Путь к файлу журнала"
            ),
            "order": 5
        }
    )
    webui_only_commands: bool = Field(
        default=True,
        description="是否只有WebUI聊天可以触发 /whatsmailog 命令",
        json_schema_extra={
            "label": "命令仅限WebUI",
            "hint": "开启后 /whatsmailog 命令仅在WebUI聊天中可用",
            "i18n": _schema_i18n(
                label_en="Commands only in WebUI",
                label_ru="Команды только в WebUI"
            ),
            "order": 6
        }
    )
    check_backend_trigger: str = Field(
        default="查你后台",
        description="触发Maisaka后台输出提取的关键词",
        json_schema_extra={
            "label": "查你后台触发词",
            "hint": "发送此关键词可提取Maisaka后台推理输出，不经过LLM总结",
            "placeholder": "查你后台",
            "i18n": _schema_i18n(
                label_en="Check backend trigger",
                label_ru="Проверка бэкенда",
                hint_en="Send this keyword to extract Maisaka backend reasoning output",
                hint_ru="Отправьте это ключевое слово для извлечения вывода системы Maisaka"
            ),
            "order": 7
        }
    )

class LLMConfig(PluginConfigBase):
    """LLM设置"""
    __ui_label__: ClassVar[str] = "大模型设置"
    __ui_order__: ClassVar[int] = 1

    enable_llm: bool = Field(
        default=True,
        description="是否启用LLM进行日志总结",
        json_schema_extra={
            "label": "启用LLM总结",
            "i18n": _schema_i18n(
                label_en="Enable LLM summary",
                label_ru="Включить сводку LLM"
            ),
            "order": 0
        }
    )
    api_key: str = Field(
        default="",
        description="DeepSeek API密钥（WebUI中会自动脱敏显示）",
        json_schema_extra={
            "label": "API密钥",
            "placeholder": "sk-...",
            "i18n": _schema_i18n(
                label_en="API Key",
                label_ru="Ключ API"
            ),
            "order": 1
        }
    )
    api_base: str = Field(
        default="https://api.deepseek.com",
        description="API地址",
        json_schema_extra={
            "label": "API地址",
            "placeholder": "https://api.deepseek.com",
            "i18n": _schema_i18n(
                label_en="API Base URL",
                label_ru="Адрес API"
            ),
            "order": 2
        }
    )
    model_name: str = Field(
        default="deepseek-chat",
        description="模型名称",
        json_schema_extra={
            "label": "模型名称",
            "placeholder": "deepseek-chat",
            "i18n": _schema_i18n(
                label_en="Model Name",
                label_ru="Название модели"
            ),
            "order": 3
        }
    )
    temperature: float = Field(
        default=0.7, ge=0.0, le=2.0,
        description="生成温度",
        json_schema_extra={
            "label": "温度 (Temperature)",
            "x-widget": "slider",
            "min": 0,
            "max": 2,
            "step": 0.1,
            "i18n": _schema_i18n(
                label_en="Temperature",
                label_ru="Температура"
            ),
            "order": 4
        }
    )

class LogWatcherConfig(PluginConfigBase):
    """插件完整配置（顶层）"""
    __ui_label__: ClassVar[str] = "日志小窥配置"
    __ui_order__: ClassVar[int] = 0

    plugin: LogWatcherPluginConfig = Field(default_factory=LogWatcherPluginConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

# ============================================================================
# 自定义 LLM Provider（继承 LLMProviderBase）
# ============================================================================
class LogWatcherLLMProvider(LLMProviderBase):
    def __init__(self, plugin: 'LogWatcherPlugin'):
        self.plugin = plugin

    async def get_response(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """实现 response 操作（文本生成）"""
        config = self.plugin.config.llm
        if not config.api_key or not config.model_name:
            raise RuntimeError("LLM 配置不完整: 请填写 API 密钥和模型名称")
        base = config.api_base.rstrip("/")
        url = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json"
        }
        messages = request.get("message_list")
        if not messages:
            raise ValueError("message_list is required")
        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": config.temperature,
            "stream": False
        }
        # 使用复用的 session（如果有）
        if self.plugin._http_session is None or self.plugin._http_session.closed:
            self.plugin._http_session = aiohttp.ClientSession()
        async with self.plugin._http_session.post(url, json=payload, headers=headers, timeout=30) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {text}")
            data = await resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("LLM 返回结果为空")
            return {"content": choices[0]["message"]["content"].strip()}

    # 本插件不需要 embedding 和 audio_transcription，可以不覆写（默认抛出 NotImplementedError）

# ============================================================================
# 插件主体
# ============================================================================
class LogWatcherPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        """插件加载时输出日志并初始化 Provider"""
        self.ctx.logger.info("[日志小窥] 插件已启动")
        self._http_session: Optional[aiohttp.ClientSession] = None
        self.provider = LogWatcherLLMProvider(self)

    async def on_unload(self) -> None:
        """插件卸载时关闭 HTTP session"""
        self.ctx.logger.info("[日志小窥] 插件已卸载")
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        """配置更新回调"""
        if scope == "self":
            self.ctx.logger.info("[日志小窥] 插件配置已更新: version=%s", version)

    config_model = LogWatcherConfig

    @property
    def _enabled(self) -> bool:
        """检查插件是否启用"""
        try:
            return bool(self.config.plugin.enabled)
        except Exception:
            return False

    # @LLMProvider 必须与 _manifest.json 中的 llm_providers[0].client_type 完全一致
    @LLMProvider(
        "1m.whatsmailog.provider",
        name="日志小窥 LLM Provider",
        description="用于总结和分析日志的 OpenAI 兼容 LLM 提供商",
        version="1.0.0"
    )
    async def handle_llm(self, operation: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Host 调用的统一入口，通过 dispatch 分发给具体的 get_response / get_embedding 等"""
        return await self.provider.dispatch(operation, request)

    # ========== 辅助方法 ==========
    def _extract_text_from_message(self, message) -> str:
        """从各种可能的消息格式中提取文本"""
        if not isinstance(message, dict):
            return ""
        # 方式1：直接 text 字段
        raw_text = message.get("text") or ""
        if raw_text:
            return raw_text
        # 方式2：raw_message.text
        raw_msg = message.get("raw_message", {})
        if isinstance(raw_msg, dict):
            raw_text = raw_msg.get("text") or ""
            if raw_text:
                return raw_text
            # raw_message.message 列表
            raw_segments = raw_msg.get("message", [])
            if isinstance(raw_segments, list):
                text_parts = []
                for seg in raw_segments:
                    if isinstance(seg, dict) and seg.get("type") == "text":
                        data = seg.get("data", {})
                        if isinstance(data, dict):
                            text_parts.append(data.get("text", ""))
                        elif isinstance(data, str):
                            text_parts.append(data)
                if text_parts:
                    return "".join(text_parts)
        elif isinstance(raw_msg, list):
            text_parts = []
            for seg in raw_msg:
                if isinstance(seg, dict) and seg.get("type") == "text":
                    data = seg.get("data", {})
                    if isinstance(data, dict):
                        text_parts.append(data.get("text", ""))
                    elif isinstance(data, str):
                        text_parts.append(data)
            if text_parts:
                return "".join(text_parts)
        # 方式3：message 段列表
        segments = message.get("message", [])
        if isinstance(segments, list):
            text_parts = []
            for seg in segments:
                if isinstance(seg, dict) and seg.get("type") == "text":
                    data = seg.get("data", {})
                    if isinstance(data, dict):
                        text_parts.append(data.get("text", ""))
                    elif isinstance(data, str):
                        text_parts.append(data)
            if text_parts:
                return "".join(text_parts)
        # 方式4：message_info.message
        msg_info = message.get("message_info", {})
        if isinstance(msg_info, dict):
            raw_text = msg_info.get("text") or ""
            if raw_text:
                return raw_text
            segments2 = msg_info.get("message", [])
            if isinstance(segments2, list):
                text_parts = []
                for seg in segments2:
                    if isinstance(seg, dict) and seg.get("type") == "text":
                        data = seg.get("data", {})
                        if isinstance(data, dict):
                            text_parts.append(data.get("text", ""))
                        elif isinstance(data, str):
                            text_parts.append(data)
                if text_parts:
                    return "".join(text_parts)
            # raw_message 在 message_info 内
            raw_msg2 = msg_info.get("raw_message", {})
            if isinstance(raw_msg2, dict):
                raw_text = raw_msg2.get("text") or ""
                if raw_text:
                    return raw_text
        return ""

    def _get_platform(self, message: dict) -> str:
        """从消息中提取平台信息（参考 Nightmare 项目）"""
        platform = message.get("platform", "")
        if platform:
            return platform
        user_info = message.get("user_info", {})
        if isinstance(user_info, dict):
            platform = user_info.get("platform", "")
            if platform:
                return platform
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            platform = message_info.get("platform", "")
            if platform:
                return platform
        return "unknown"

    # ========== 日志获取 ==========
    def _resolve_log_path(self, log_path: str) -> str:
        """
        解析日志路径，支持 MaiBot 的 JSONL 格式日志。
        MaiBot 日志格式：logs/app_YYYYMMDD_HHMMSS.log.jsonl
        """
        # 如果 log_path 是目录，查找最新的 .jsonl 文件
        if os.path.isdir(log_path):
            jsonl_files = sorted(
                [f for f in os.listdir(log_path) if f.startswith("app_") and f.endswith(".log.jsonl")],
                reverse=True,
            )
            if jsonl_files:
                resolved = os.path.join(log_path, jsonl_files[0])
                self.ctx.logger.info(f"[日志小窥] 日志目录中找到最新日志文件: {resolved}")
                return resolved
            self.ctx.logger.warning(f"[日志小窥] 日志目录中无 .jsonl 文件: {log_path}")
            return log_path

        # 如果 log_path 是文件路径但不存在，尝试在 logs/ 目录下查找
        if not os.path.exists(log_path) and not os.path.isabs(log_path):
            # 尝试从工作目录的 logs/ 子目录查找
            alt_path = os.path.join("logs", os.path.basename(log_path))
            if os.path.exists(alt_path):
                self.ctx.logger.info(f"[日志小窥] 使用备用日志路径: {alt_path}")
                return alt_path

            # 尝试在 logs/ 目录下查找最新的 .jsonl 文件
            if os.path.isdir("logs"):
                jsonl_files = sorted(
                    [f for f in os.listdir("logs") if f.startswith("app_") and f.endswith(".log.jsonl")],
                    reverse=True,
                )
                if jsonl_files:
                    resolved = os.path.join("logs", jsonl_files[0])
                    self.ctx.logger.info(f"[日志小窥] 使用最新日志文件: {resolved}")
                    return resolved

        # 尝试常见的日志目录
        for candidate in [
            "/MaiMBot/logs",
            "/app/logs",
            os.path.join(os.getcwd(), "logs"),
        ]:
            if os.path.isdir(candidate):
                jsonl_files = sorted(
                    [f for f in os.listdir(candidate) if f.startswith("app_") and f.endswith(".log.jsonl")],
                    reverse=True,
                )
                if jsonl_files:
                    resolved = os.path.join(candidate, jsonl_files[0])
                    self.ctx.logger.info(f"[日志小窥] 找到日志文件: {resolved}")
                    return resolved

        return log_path

    def _parse_log_line(self, line: str) -> Optional[tuple]:
        """
        解析单行日志，返回 (timestamp, formatted_text) 或 None
        支持 JSONL 格式和普通文本格式
        """
        import json

        line = line.strip()
        if not line:
            return None

        # 尝试解析 JSONL 格式
        try:
            log_entry = json.loads(line)
            ts_str = log_entry.get("timestamp", "")

            # 解析时间戳
            log_timestamp = None
            if ts_str:
                try:
                    if "T" in ts_str:
                        log_timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00").replace("+00:00", ""))
                    else:
                        log_timestamp = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    pass

            # 提取日志内容
            event_text = log_entry.get("event", "")
            level_text = log_entry.get("level", "")
            module_text = log_entry.get("logger_name") or log_entry.get("module") or ""

            # 构建可读的日志文本
            if event_text:
                log_text = f"[{ts_str}] [{level_text}] [{module_text}] {event_text}" if ts_str else event_text
            else:
                log_text = line

            return (log_timestamp, log_text)

        except json.JSONDecodeError:
            pass

        # 尝试普通文本格式 [YYYY-MM-DD HH:MM:SS] ...
        log_timestamp = None
        if line.startswith('[') and ']' in line:
            possible_time = line[1:line.find(']')]
            try:
                log_timestamp = datetime.strptime(possible_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        return (log_timestamp, line)

    async def _get_logs(self, minutes: int, max_lines: int, log_path: str) -> List[str]:
        """
        获取最近几分钟的日志内容
        支持 MaiBot JSONL 格式日志和普通文本日志
        JSONL 格式：{"timestamp": "...", "level": "...", "event": "...", ...}

        策略：先获取当前时间 -> 读取所有日志 -> 按时间过滤 -> 取最新的 max_lines 条
        """
        import json

        # 1. 先获取当前时间
        now = datetime.now()
        start_time = now - timedelta(minutes=minutes)
        self.ctx.logger.info(f"[日志小窥] 获取日志: now={now}, start_time={start_time}, minutes={minutes}")

        # 2. 解析正确的日志路径
        resolved_path = self._resolve_log_path(log_path)
        self.ctx.logger.info(f"[日志小窥] 日志文件解析路径: {log_path} -> {resolved_path}")

        if not os.path.exists(resolved_path):
            self.ctx.logger.warning(f"[日志小窥] 日志文件不存在: {resolved_path}")
            return [f"日志文件不存在: {resolved_path}"]

        try:
            # 3. 读取所有日志行
            with open(resolved_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            self.ctx.logger.info(f"[日志小窥] 读取到 {len(lines)} 行日志")

            # 4. 解析所有日志并过滤
            all_logs = []
            for line in lines:
                parsed = self._parse_log_line(line)
                if parsed is None:
                    continue

                log_timestamp, log_text = parsed
                all_logs.append((log_timestamp, log_text))

            # 5. 按时间过滤，只保留最近 minutes 分钟内的日志
            filtered_logs = []
            for log_timestamp, log_text in all_logs:
                if log_timestamp is not None:
                    # 有时间戳，检查是否在时间范围内
                    if log_timestamp >= start_time:
                        filtered_logs.append((log_timestamp, log_text))
                else:
                    # 没有时间戳，保留（可能是格式不认识的日志）
                    filtered_logs.append((log_timestamp, log_text))

            self.ctx.logger.info(f"[日志小窥] 时间过滤后剩余 {len(filtered_logs)} 行日志")

            # 6. 按时间排序（最新的在前），取最新的 max_lines 条
            # reverse=True 让最新的日志排在前面
            filtered_logs.sort(key=lambda x: x[0] if x[0] else datetime.min, reverse=True)

            # 取最新的 max_lines 条
            latest_logs = filtered_logs[:max_lines]

            # 7. 反转回时间正序（旧的在前，新的在后）
            latest_logs.reverse()

            if not latest_logs:
                return [f"最近 {minutes} 分钟内无日志记录"]

            # 返回格式化后的文本列表
            return [log_text for _, log_text in latest_logs]

        except Exception as e:
            self.ctx.logger.error("[日志小窥] 读取日志失败: %s", e, exc_info=True)
            return [f"读取日志时出错: {str(e)}"]

    async def _generate_summary(self, logs: List[str]) -> str:
        """调用 LLM 生成日志总结（通过 Provider）"""
        if not self.config.llm.enable_llm:
            return "（LLM总结未启用）"

        # 限制日志长度，避免超出 token 限制
        log_text = "\n".join(logs[-50:])
        if len(log_text) > 8000:
            log_text = log_text[:8000] + "\n...(已截断)"

        prompt = (
            "你是一个专业的日志分析助手。请根据以下最近的日志内容，生成一个简洁的中文总结（150字以内）：\n"
            "- 重点指出 ERROR 或 CRITICAL 级别的错误\n"
            "- 总结主要的功能调用、异常情况和整体运行状态\n"
            "- 不要包含用户昵称等隐私信息\n\n"
            f"日志内容：\n{log_text}"
        )
        try:
            response = await self.provider.get_response({
                "message_list": [{"role": "user", "content": prompt}]
            })
            content = response.get("content", "").strip()
            return content if content else "生成总结失败"
        except Exception as e:
            self.ctx.logger.error("[日志小窥] LLM调用失败: %s", e, exc_info=True)
            return f"LLM调用失败: {str(e)}"

    async def _send_log_report(self, stream_id: str) -> None:
        """发送日志报告的核心逻辑（供命令复用）"""
        minutes = self.config.plugin.log_minutes
        max_lines = self.config.plugin.max_log_lines
        log_path = self.config.plugin.log_file_path

        logs = await self._get_logs(minutes, max_lines, log_path)
        summary = await self._generate_summary(logs)

        # 检查是否有错误
        has_error = any("ERROR" in log or "CRITICAL" in log for log in logs)

        # 构建回复消息
        now = datetime.now().strftime("%H:%M:%S")
        if has_error:
            reply = f"⚠️ 检测到最近{minutes}分钟内出现错误！\n{summary}\n[看看日志]"
        else:
            reply = f"📋 最近{minutes}分钟的日志总结：\n{summary}\n[看看日志]"

        # 添加最新日志片段（最多3行）
        if logs and len(logs) > 0:
            recent_logs = [log for log in logs[-3:] if log.strip()]
            if recent_logs:
                reply += f"\n\n--- 最新日志片段 ---\n" + "\n".join(recent_logs)

        # 添加时间戳
        reply += f"\n\n🕐 报告时间: {now}"

        await self.ctx.send.text(reply, stream_id)
        self.ctx.logger.info("[日志小窥] 已向 %s 发送日志报告", stream_id)

    def _build_trigger_pattern(self) -> str:
        """从配置构建触发词正则表达式"""
        trigger_phrases = self.config.plugin.trigger_phrases
        if not trigger_phrases:
            # 默认触发词
            trigger_phrases = ["发生什么了", "是不是哪里出问题了"]

        # 转义特殊字符并构建正则
        escaped = [re.escape(phrase) for phrase in trigger_phrases]
        pattern = "|".join(escaped)
        self.ctx.logger.info(f"[日志小窥] 构建触发词正则: {pattern}")
        return pattern

    # ========== 命令处理器 ==========
    @Command(
        name="log_query",
        description="触发日志查看（自定义触发词，不受WebUI限制）",
        pattern=r"(发生什么了|发生什么事了|是不是哪里出问题了)"  # 默认值，实际使用 _build_trigger_pattern 动态判断
    )
    async def on_log_query(self, **kwargs):
        """当用户发送触发词时调用 - 触发词形式，不受 webui_only_commands 限制"""
        if not self._enabled:
            return False, "插件未启用", 0

        # 获取原始消息内容
        message = kwargs.get("message", {})
        raw_text = self._extract_text_from_message(message)

        if not raw_text:
            self.ctx.logger.warning("[日志小窥] 无法获取消息文本，跳过触发词检测")
            self.ctx.logger.debug("[日志小窥] message 结构: %s", str(message)[:500])
            return False, "无消息文本", 0

        # 动态构建触发词正则并检测
        pattern = self._build_trigger_pattern()
        if not re.search(pattern, raw_text):
            # 未匹配到触发词
            return False, "未匹配触发词", 0

        self.ctx.logger.info(f"[日志小窥] 触发词匹配成功: {raw_text[:50]}")

        stream_id = kwargs.get("stream_id", "")
        if not stream_id:
            self.ctx.logger.warning("[日志小窥] stream_id 为空，无法发送日志报告")
            return False, "stream_id 为空", 0

        # 触发词形式不受 webui_only_commands 限制，所有平台可用
        await self._send_log_report(stream_id)
        return True, "日志报告已发送", 1

    @Command(
        name="whatsmailog",
        description="手动触发日志查看（仅WebUI）",
        pattern=r"^/whatsmailog$"
    )
    async def on_whatsmailog(self, **kwargs):
        """手动触发日志查看，仅在 WebUI 生效（可配置）"""
        if not self._enabled:
            return False, "插件未启用", 0

        message = kwargs.get("message", {})
        platform = self._get_platform(message)

        # 检查是否仅限 WebUI
        if self.config.plugin.webui_only_commands and platform != "webui":
            self.ctx.logger.info("[日志小窥] /whatsmailog 命令在非WebUI平台被触发，已忽略。平台=%s", platform)
            return False, "此命令仅在WebUI中可用", 0

        stream_id = kwargs.get("stream_id", "")
        if not stream_id:
            self.ctx.logger.warning("[日志小窥] stream_id 为空，无法发送日志报告")
            return False, "stream_id 为空", 0

        await self._send_log_report(stream_id)
        return True, "日志报告已发送", 1

    @Command(
        name="llmtest",
        description="测试 LLM Provider 连接",
        pattern=r"^/llmtest$"
    )
    async def on_llmtest(self, **kwargs):
        """测试 LLM Provider 是否正常工作 - /xx 形式命令，受 webui_only_commands 限制"""
        if not self._enabled:
            await self.ctx.send.text("❌ 插件未启用", kwargs.get("stream_id", ""))
            return False, "插件未启用", 0

        message = kwargs.get("message", {})
        platform = self._get_platform(message)

        # /xx 形式命令受 webui_only_commands 限制
        if self.config.plugin.webui_only_commands and platform != "webui":
            self.ctx.logger.info("[日志小窥] /llmtest 命令在非WebUI平台被触发，已忽略。平台=%s", platform)
            return False, "此命令仅在WebUI中可用", 0

        stream_id = kwargs.get("stream_id", "")
        config = self.config.llm

        if not config.enable_llm:
            await self.ctx.send.text("❌ LLM 总结未启用", stream_id)
            return False, "LLM 未启用", 0

        if not config.api_key or not config.model_name:
            await self.ctx.send.text("❌ LLM 配置不完整：请填写 API 密钥和模型名称", stream_id)
            return False, "LLM 配置不完整", 0

        try:
            test_request = {
                "message_list": [{"role": "user", "content": "请用中文回复'连接成功'，不要加任何其他内容。"}]
            }
            response = await self.provider.get_response(test_request)
            result = response.get("content", "")
            self.ctx.logger.info("[日志小窥] LLM 提供商测试成功，返回: %s", result)
            await self.ctx.send.text(f"✅ LLM 提供商测试成功，回复: {result}", stream_id)
            return True, "测试成功", 1
        except Exception as e:
            self.ctx.logger.error("[日志小窥] LLM 提供商测试失败: %s", e, exc_info=True)
            await self.ctx.send.text(f"❌ LLM 提供商测试失败: {e}", stream_id)
            return False, f"测试失败: {e}", 0

    @Command(
        name="logpath",
        description="查看当前日志文件路径",
        pattern=r"^/logpath$"
    )
    async def on_logpath(self, **kwargs):
        """查看当前配置的日志文件路径 - /xx 形式命令，受 webui_only_commands 限制"""
        if not self._enabled:
            return False, "插件未启用", 0

        message = kwargs.get("message", {})
        platform = self._get_platform(message)

        # /xx 形式命令受 webui_only_commands 限制
        if self.config.plugin.webui_only_commands and platform != "webui":
            self.ctx.logger.info("[日志小窥] /logpath 命令在非WebUI平台被触发，已忽略。平台=%s", platform)
            return False, "此命令仅在WebUI中可用", 0

        stream_id = kwargs.get("stream_id", "")
        log_path = self.config.plugin.log_file_path
        exists = os.path.exists(log_path)
        status = "✅ 存在" if exists else "❌ 不存在"
        await self.ctx.send.text(f"📂 当前日志文件路径: {log_path}\n状态: {status}", stream_id)
        return True, "已显示日志路径", 1

    @Command(
        name="check_backend",
        description="提取最近的Maisaka后台输出",
        pattern=r"^/check_backend$"
    )
    async def on_check_backend(self, **kwargs):
        """提取最近的Maisaka后台输出并直接发送至聊天流（不经过LLM总结）"""
        if not self._enabled:
            return False, "插件未启用", 0

        message = kwargs.get("message", {})
        platform = self._get_platform(message)

        # /xx 形式命令受 webui_only_commands 限制
        if self.config.plugin.webui_only_commands and platform != "webui":
            self.ctx.logger.info("[日志小窥] /check_backend 命令在非WebUI平台被触发，已忽略。平台=%s", platform)
            return False, "此命令仅在WebUI中可用", 0

        stream_id = kwargs.get("stream_id", "")
        if not stream_id:
            self.ctx.logger.warning("[日志小窥] stream_id 为空，无法发送")
            return False, "stream_id 为空", 0

        # 获取配置
        minutes = self.config.plugin.log_minutes
        log_path = self.config.plugin.log_file_path

        self.ctx.logger.info(f"[日志小窥] 查你后台: 查找最近{minutes}分钟的Maisaka输出")

        # 提取Maisaka输出
        maisaka_output = await self._extract_maisaka_output(minutes, log_path)

        if maisaka_output:
            # 截断过长的输出
            if len(maisaka_output) > 4000:
                maisaka_output = maisaka_output[:4000] + "\n\n...(输出已截断)"
            await self.ctx.send.text(f"🔍 Maisaka 后台输出（最近{minutes}分钟）：\n\n{maisaka_output}", stream_id)
            self.ctx.logger.info("[日志小窥] 已向 %s 发送Maisaka后台输出", stream_id)
            return True, "Maisaka后台输出已发送", 1
        else:
            await self.ctx.send.text(f"📋 最近{minutes}分钟内未检测到Maisaka后台输出。", stream_id)
            self.ctx.logger.info("[日志小窥] 最近{minutes}分钟内无Maisaka输出")
            return True, "未检测到Maisaka输出", 1

    async def _extract_maisaka_output(self, minutes: int, log_path: str) -> Optional[str]:
        """
        从日志中提取最近一次Maisaka返回的纯文本（不经过LLM总结）
        读取目录下所有最近的JSONL文件，确保不漏掉刚写入的日志
        """
        now = datetime.now()
        start_time = now - timedelta(minutes=minutes)

        # 收集所有需要扫描的日志文件
        log_files = self._find_log_files(log_path, start_time)
        if not log_files:
            self.ctx.logger.warning(f"[日志小窥] 未找到日志文件: {log_path}")
            return None

        self.ctx.logger.info(f"[日志小窥] 扫描 {len(log_files)} 个日志文件: {[os.path.basename(f) for f in log_files]}")

        try:
            maisaka_entries = []  # (timestamp, event_text)

            for file_path in log_files:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw_lines = f.readlines()

                for raw_line in raw_lines:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        log_entry = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    ts_str = log_entry.get("timestamp", "")
                    log_timestamp = None
                    if ts_str:
                        try:
                            if "T" in ts_str:
                                log_timestamp = datetime.fromisoformat(
                                    ts_str.replace("Z", "+00:00").replace("+00:00", "")
                                )
                            else:
                                log_timestamp = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                        except (ValueError, TypeError):
                            pass

                    # 时间过滤
                    if log_timestamp is not None and log_timestamp < start_time:
                        continue

                    event_text = log_entry.get("event") or ""

                    # 识别包含"Maisaka 返回"标记的event（框线中的推理输出）
                    if "Maisaka 返回" in event_text or "MaiSaka 返回" in event_text:
                        maisaka_entries.append((log_timestamp, event_text))

            if not maisaka_entries:
                return None

            # 按时间排序，取最新一条
            maisaka_entries.sort(key=lambda x: x[0] if x[0] else datetime.min, reverse=True)
            latest_event = maisaka_entries[0][1]

            # 提取 Maisaka 返回部分的纯文本，去除框线
            # 事件文本格式（JSONL中为\n分隔的完整框）：
            # ╭─ Maisaka 返回 ─╮
            # │ 实际内容...    │
            # ╰───────────────╯
            lines = latest_event.split('\n')
            result_lines = []
            in_return_block = False

            for line in lines:
                stripped = line.strip()
                if "Maisaka 返回" in line or "MaiSaka 返回" in line:
                    in_return_block = True
                    continue
                if in_return_block and stripped.startswith('╰') and '─' in stripped:
                    break
                if in_return_block:
                    # 去除框线字符
                    if '│' in line:
                        idx = line.index('│')
                        cleaned = line[idx + 1:]
                        if '│' in cleaned:
                            cleaned = cleaned[: cleaned.rindex('│')]
                        cleaned = cleaned.strip()
                    else:
                        cleaned = line.replace('─', '').strip()
                    if cleaned:
                        result_lines.append(cleaned)

            if result_lines:
                return "\n".join(result_lines)

            return None

        except Exception as e:
            self.ctx.logger.error("[日志小窥] 提取Maisaka输出失败: %s", e, exc_info=True)
            return None

    def _find_log_files(self, log_path: str, start_time: datetime) -> List[str]:
        """查找可能包含目标时间范围内日志的所有 JSONL 文件"""
        # 解析基础目录
        base_dir = log_path if os.path.isdir(log_path) else os.path.dirname(log_path)
        if not base_dir or base_dir == "":
            base_dir = "logs"

        if not os.path.isdir(base_dir):
            # 尝试解析为文件路径
            resolved = self._resolve_log_path(log_path)
            if os.path.isfile(resolved):
                return [resolved]
            # 回退到 logs/ 目录
            if os.path.isdir("logs"):
                base_dir = "logs"
            else:
                return []

        # 收集文件名包含 time 范围的 .jsonl 文件
        candidates = []
        for fname in os.listdir(base_dir):
            if not (fname.startswith("app_") and fname.endswith(".log.jsonl")):
                continue
            # 从文件名提取时间: app_YYYYMMDD_HHMMSS.log.jsonl
            try:
                ts_part = fname[4:19]  # "YYYYMMDD_HHMMSS"
                file_ts = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
            except (ValueError, IndexError):
                candidates.append(os.path.join(base_dir, fname))
                continue

            # 文件时间在 start_time 之后（前15分钟缓冲），说明可能包含相关日志
            if file_ts >= (start_time - timedelta(minutes=15)):
                candidates.append(os.path.join(base_dir, fname))

        # 确保至少包含最新文件
        if not candidates:
            resolved = self._resolve_log_path(log_path)
            if os.path.isfile(resolved):
                return [resolved]

        candidates.sort(reverse=True)
        # 最多读取3个最新文件
        return candidates[:3]

    # 触发词形式的"查你后台"（不受WebUI限制）
    @Command(
        name="check_backend_trigger",
        description="触发词形式的查你后台（不受WebUI限制）",
        pattern=r"^(查你后台|查看后台|backend)$"
    )
    async def on_check_backend_trigger(self, **kwargs):
        """触发词形式的查你后台 - 触发词形式，不受 webui_only_commands 限制"""
        if not self._enabled:
            return False, "插件未启用", 0

        stream_id = kwargs.get("stream_id", "")
        if not stream_id:
            return False, "stream_id 为空", 0

        # 复用核心逻辑
        minutes = self.config.plugin.log_minutes
        log_path = self.config.plugin.log_file_path

        maisaka_output = await self._extract_maisaka_output(minutes, log_path)

        if maisaka_output:
            if len(maisaka_output) > 4000:
                maisaka_output = maisaka_output[:4000] + "\n\n...(输出已截断)"
            await self.ctx.send.text(f"🔍 Maisaka 后台输出（最近{minutes}分钟）：\n\n{maisaka_output}", stream_id)
            return True, "Maisaka后台输出已发送", 1
        else:
            await self.ctx.send.text(f"📋 最近{minutes}分钟内未检测到Maisaka后台输出。", stream_id)
            return True, "未检测到Maisaka输出", 1


def create_plugin():
    return LogWatcherPlugin()

# try15 - 2026-07-11 优化日志获取逻辑：_find_log_files 扫描多个JSONL文件防止漏读；MaiBot日志架构分析