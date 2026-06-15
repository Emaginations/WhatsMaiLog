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
"""

from maibot_sdk import Field, MaiBotPlugin, LLMProvider, LLMProviderBase, Command, PluginConfigBase
from typing import ClassVar, List, Any, Dict, Optional
from datetime import datetime, timedelta
import aiohttp
import os

# ============================================================================
# 多语言化支持（中文、俄语）
# ============================================================================
def _schema_i18n(
    label_zh: str,
    label_ru: str,
    hint_zh: Optional[str] = None,
    hint_ru: Optional[str] = None,
    placeholder_zh: Optional[str] = None,
    placeholder_ru: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    i18n = {
        "zh-CN": {"label": label_zh},
        "ru-RU": {"label": label_ru},
    }
    if hint_zh:
        i18n["zh-CN"]["hint"] = hint_zh
    if hint_ru:
        i18n["ru-RU"]["hint"] = hint_ru
    if placeholder_zh:
        i18n["zh-CN"]["placeholder"] = placeholder_zh
    if placeholder_ru:
        i18n["ru-RU"]["placeholder"] = placeholder_ru
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
            "i18n": _schema_i18n("开关", "Включить"),
            "order": 0
        }
    )
    trigger_phrases: List[str] = Field(
        default=["发生什么了{bot_name}", "是不是哪里出问题了"],
        description="触发关键词列表，可使用{bot_name}占位符",
        json_schema_extra={
            "label": "触发词",
            "i18n": _schema_i18n(
                "触发词", "Ключевые слова",
                "用户发送这些消息时触发插件", "Плагин срабатывает при отправке этих сообщений"
            ),
            "order": 1
        }
    )
    log_minutes: int = Field(
        default=10, ge=1, le=60,
        description="查询日志的时间范围（分钟）",
        json_schema_extra={
            "label": "查询范围（分钟）",
            "i18n": _schema_i18n("查询范围（分钟）", "Диапазон запроса (минуты)"),
            "order": 2
        }
    )
    max_log_lines: int = Field(
        default=50, ge=10, le=200,
        description="最多获取的日志行数",
        json_schema_extra={
            "label": "最大日志行数",
            "i18n": _schema_i18n("最大日志行数", "Максимальное количество строк журнала"),
            "order": 3
        }
    )
    log_file_path: str = Field(
        default="logs/maibot.log",
        description="日志文件路径（相对或绝对路径）",
        json_schema_extra={
            "label": "日志文件路径",
            "i18n": _schema_i18n("日志文件路径", "Путь к файлу журнала"),
            "order": 4
        }
    )
    webui_only_commands: bool = Field(
        default=True,
        description="是否只有WebUI聊天可以触发 /whatsmailog 命令",
        json_schema_extra={
            "label": "命令仅限WebUI",
            "i18n": _schema_i18n("命令仅限WebUI", "Команды только в WebUI"),
            "order": 5
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
            "i18n": _schema_i18n("启用LLM总结", "Включить сводку LLM"),
            "order": 0
        }
    )
    api_key: str = Field(
        default="",
        description="DeepSeek API密钥（WebUI中会自动脱敏显示）",
        json_schema_extra={
            "label": "API密钥",
            "i18n": _schema_i18n("API密钥", "Ключ API"),
            "order": 1
        }
    )
    api_base: str = Field(
        default="https://api.deepseek.com",
        description="API地址",
        json_schema_extra={
            "label": "API地址",
            "i18n": _schema_i18n("API地址", "Адрес API"),
            "order": 2
        }
    )
    model_name: str = Field(
        default="deepseek-chat",
        description="模型名称",
        json_schema_extra={
            "label": "模型名称",
            "i18n": _schema_i18n("模型名称", "Название модели"),
            "order": 3
        }
    )
    temperature: float = Field(
        default=0.7, ge=0.0, le=2.0,
        description="生成温度",
        json_schema_extra={
            "label": "温度",
            "i18n": _schema_i18n("温度", "Температура"),
            "x-widget": "slider",
            "min": 0,
            "max": 2,
            "step": 0.1,
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
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=30) as resp:
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
        # 插件加载时输出日志（符合 logger API 要求）
        self.ctx.logger.info("[日志小窥] 插件已启动")
        self.provider = LogWatcherLLMProvider(self)

    async def on_unload(self) -> None:
        self.ctx.logger.info("[日志小窥] 插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("[日志小窥] 插件配置已更新: version=%s", version)

    config_model = LogWatcherConfig

    # @LLMProvider 必须与 _manifest.json 中的 llm_providers[0].client_type 完全一致
    @LLMProvider(
        "1m.whatsmailog.provider",
        name="日志小窥 LLM Provider",
        description="用于总结和分析日志",
        version="1.0.0"
    )
    async def handle_llm(self, operation: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Host 调用的统一入口，通过 dispatch 分发给具体的 get_response / get_embedding 等"""
        return await self.provider.dispatch(operation, request)

    # ========== 辅助方法 ==========
    def _get_platform(self, message: dict) -> str:
        """从消息中提取平台信息"""
        platform = message.get("platform", "")
        if platform:
            return platform
        user_info = message.get("user_info", {})
        platform = user_info.get("platform", "")
        if platform:
            return platform
        message_info = message.get("message_info", {})
        platform = message_info.get("platform", "")
        if platform:
            return platform
        return "unknown"

    # ========== 日志获取 ==========
    async def _get_logs(self, minutes: int, max_lines: int, log_path: str) -> List[str]:
        """获取最近几分钟的日志内容（通过读取日志文件）"""
        now = datetime.now()
        start_time = now - timedelta(minutes=minutes)
        logs = []
        try:
            if not os.path.exists(log_path):
                self.ctx.logger.warning(f"[日志小窥] 日志文件不存在: {log_path}")
                return [f"日志文件不存在: {log_path}"]

            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            collected = []
            for line in reversed(lines):
                if len(collected) >= max_lines:
                    break
                time_str = None
                if line.startswith('[') and ']' in line:
                    possible_time = line[1:line.find(']')]
                    try:
                        dt = datetime.strptime(possible_time, "%Y-%m-%d %H:%M:%S")
                        if dt >= start_time:
                            time_str = possible_time
                    except:
                        pass
                if time_str is None:
                    collected.append(line.strip())
                else:
                    if datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S") >= start_time:
                        collected.append(line.strip())
            collected.reverse()
            return collected if collected else [f"最近 {minutes} 分钟内无日志记录"]
        except Exception as e:
            self.ctx.logger.error(f"[日志小窥] 读取日志失败: {e}", exc_info=True)
            return [f"读取日志时出错: {str(e)}"]

    async def _generate_summary(self, logs: List[str]) -> str:
        """调用 LLM 生成日志总结（通过 Provider）"""
        if not self.config.llm.enable_llm:
            return "（LLM总结未启用）"

        log_text = "\n".join(logs[-50:])
        if len(log_text) > 8000:
            log_text = log_text[:8000] + "\n...(已截断)"

        prompt = f"""
你是一个日志分析助手。请根据以下最近的日志内容，生成一个简要的中文总结（200字以内）：
- 如果有错误（ERROR 或 CRITICAL 级别），请明确指出并重点提示。
- 总结主要的功能调用、异常情况和整体运行状态。

日志内容：
{log_text}
"""
        try:
            response = await self.provider.get_response({
                "message_list": [{"role": "user", "content": prompt}]
            })
            return response.get("content", "生成总结失败")
        except Exception as e:
            self.ctx.logger.error(f"[日志小窥] LLM调用失败: {e}", exc_info=True)
            return f"LLM调用失败: {str(e)}"

    async def _send_log_report(self, stream_id: str) -> None:
        """发送日志报告的核心逻辑（供命令复用）"""
        minutes = self.config.plugin.log_minutes
        max_lines = self.config.plugin.max_log_lines
        log_path = self.config.plugin.log_file_path

        logs = await self._get_logs(minutes, max_lines, log_path)
        summary = await self._generate_summary(logs)

        has_error = any("ERROR" in log or "CRITICAL" in log for log in logs)

        if has_error:
            reply = f"⚠️ 检测到最近{minutes}分钟内出现错误！\n{summary}\n[看看日志]"
        else:
            reply = f"📋 最近{minutes}分钟的日志总结：\n{summary}\n[看看日志]"

        if logs:
            log_preview = "\n".join(logs[-3:])
            if log_preview:
                reply += f"\n\n--- 最新日志片段 ---\n{log_preview}"

        await self.ctx.send.text(reply, stream_id)
        self.ctx.logger.info(f"[日志小窥] 已向 {stream_id} 发送日志报告")

    # ========== 命令处理器 ==========
    # 命令1：用户自定义触发词（正常使用）
    @Command(
        name="log_query",
        description="触发日志查看",
        pattern=r"(发生什么了|是不是哪里出问题了)"
    )
    async def on_log_query(self, **kwargs):
        """当用户发送触发词时调用"""
        if not self.config.plugin.enabled:
            return False, "插件未启用", 0

        stream_id = kwargs["stream_id"]
        await self._send_log_report(stream_id)
        return True, "日志报告已发送", 1

    # 命令2：手动触发命令 /whatsmailog（仅WebUI生效）
    @Command(
        name="whatsmailog",
        description="手动触发日志查看（仅WebUI）",
        pattern=r"^/whatsmailog$"
    )
    async def on_whatsmailog(self, **kwargs):
        """手动触发日志查看，仅在 WebUI 生效（可配置）"""
        if not self.config.plugin.enabled:
            return False, "插件未启用", 0

        message = kwargs.get("message", {})
        platform = self._get_platform(message)

        # 检查是否仅限 WebUI
        if self.config.plugin.webui_only_commands and platform != "webui":
            self.ctx.logger.info(f"[日志小窥] /whatsmailog 命令在非WebUI平台被触发，已忽略。平台={platform}")
            return False, "此命令仅在WebUI中可用", 0

        stream_id = kwargs["stream_id"]
        await self._send_log_report(stream_id)
        return True, "日志报告已发送", 1

    # 命令3：LLM连接测试命令 /llmtest（所有平台可用）
    @Command(
        name="llmtest",
        description="测试 LLM Provider 连接",
        pattern=r"^/llmtest$"
    )
    async def on_llmtest(self, **kwargs):
        """测试 LLM Provider 是否正常工作"""
        if not self.config.plugin.enabled:
            await self.ctx.send.text("❌ 插件未启用", kwargs["stream_id"])
            return False, "插件未启用", 0

        stream_id = kwargs["stream_id"]
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
            self.ctx.logger.info(f"[日志小窥] LLM 提供商测试成功，返回: {result}")
            await self.ctx.send.text(f"✅ LLM 提供商测试成功，回复: {result}", stream_id)
            return True, "测试成功", 1
        except Exception as e:
            self.ctx.logger.error(f"[日志小窥] LLM 提供商测试失败: {e}", exc_info=True)
            await self.ctx.send.text(f"❌ LLM 提供商测试失败: {e}", stream_id)
            return False, f"测试失败: {e}", 0


def create_plugin():
    return LogWatcherPlugin()

# try8