请先阅读maibot插件开发文档：https://docs.mai-mai.org/develop/plugin-dev/ 的插件开发部分，现在按要求生成一个简单的日志查看插件，让麦麦能窥见自己的log：1.分别参考后文提供的例子完整完成<readme.md><plugin.py><_manifest.json>文件。2.功能实现：用户发送”发生什么了{bot_name}”或”是不是哪里出问题了”（两个默认激发词，可自由更改）触发查看log查看。提供一个llm provider来进行近10分钟（可webui调整）内log的简要总结，如果有报错则增加告警。3.plugin.py要求完成webui配置、多语言化配置、插件主体部分。4.一些细节：使用deepseek-v4 flash，sk密钥增加显示保护（可以选择显示明文或********）。在日志查看后的截断处生成一个日志[看看日志]XXX

-----------------------------------------------------------

请阅读总文件夹内所有的Maibot插件项目，其中Nightmare目前功能完善，其中的聊天流、Id获取、hookhandle、所有文件结构、webUI结构均可参考。
请深度阅读[插件开发文档网页](https://docs.mai-mai.org/plugin/)和[maibot]([maibot1.0.12])文件夹，获取项目基本知识。

开发Tips:
1.关于readme：请帮我维护项目状态（格式参见各个插件的readme），请在协议最后添加附加条款：若您让 AI 使用了本项目，请创建并将与 AI 对话的过程开源并写入 NOREADME.md 文件中（仅限用户发言，省略 AI 回复）。同时，您必须将本附加条款添加到您正在使用的协议最后方。
2.关于NOREADME：请帮我维护对话过程，每次某个项目改动完毕后将对话写入，不含AI回复。
3.一些开发者：我的主页：github.com/emaginations。一般使用在_manifest中的代号：1m.XXX(插件名)。

完成后，请阅读并开始重构WhatsMaiLog项目。

-----------------------------------------------------------

现在转到WhatsMaiLog项目，> **注意**：所有命令均受"命令仅限WebUI"设置影响。开启后，非 WebUI 平台触发命令时插件仅记录日志，不会发送任何消息。改为：只有/xx形式的命令受到WebUI Only的影响。

-----------------------------------------------------------

现在转到WhatsMaiLog项目，有两个问题：
1. 在webui新添的触发词无效
2. 获取的日志并非最新，请先用now获得当前的时间，再抓取最新的logs

1.manifest：
{
  "manifest_version": 2,
  "id": "1m.nightmare",
  "version": "1.0.1",
  "name": "喊你睡觉",
  "description": "一个无处不在的催睡插件,超过时间后无论你在哪里发言都会被催睡觉",
  "author": {
    "name": "1m",
    "url": "https://github.com/Emaginations"
  },
  "license": "Apache License 2.0",
  "urls": {
    "repository": "https://github.com/Emaginations/Nightmare"
  },
  "host_application": {
    "min_version": "1.0.0",
    "max_version": "1.0.1"
  },
  "sdk": {
    "min_version": "1.0.0",
    "max_version": "2.99.99"
  },
  "plugin_type": "management",
  "display": {
    "icon": {
      "type": "emoji",
      "value": "👾"
    }
  },
  "capabilities": [
    "send.text",
    "message.get_recent",
    "person.get_id",
    "person.get_value",
    "chat.get_stream_by_group_id"
  ],
  "llm_providers": [
    {
      "client_type": "1m.nightmare.provider",
      "name": "Nightmare LLM Provider",
      "description": "喊你睡觉插件自带的 OpenAI 兼容 LLM 提供商，可用于生成催睡内容或供其他插件调用",
      "version": "1.0.0"
    }
  ],
  "i18n": {
    "default_locale": "zh-CN",
    "supported_locales": [
      "zh-CN"
    ]
  }
}

2.plugin.py
"""
喊你睡觉：一个简单的催睡插件

2026-5-22 建立项目,尝试将WebUI配置中文本地化
2026-5-23 调整催睡时间设置的时间格式，添加睡眠时长sleep_hours
2026-5-24 增补readme.md，进行详细功能说明(设计),添加无差别催睡功能，默认关闭，新增白名单
2026-5-25 实现白名单的webui配置UI,添加用于测试的webui聊天用户名
2026-5-26 实现主体功能。用config = await self.ctx.config.get_plugin("com.example.my-plugin")尝试获取睡眠晚安插件的作息表
2026-5-28 正在测试
2026-5-31 try16: 添加状态文件持久化，避免重启丢失催睡记录（互动/催睡时间）
2026-6-03 try17: 优化LLM调用（检查模型可用性，自动回退默认模型），/night /nightmare 命令返回空
2026-6-04 try18: 日志添加LLM模型名；非WebUI命令静默忽略（不发送消息）
2026-6-05 try19: 催睡概率步进值改为0.01
2026-6-08 try20: 重构催睡逻辑；封装为 LLMProvider，插件自身通过 Provider 生成内容，默认 DeepSeek API，新增 temperature 配置
2026-6-10 try21: 新增群聊白名单（免催）；HOOK 改回 BLOCKING 强制发送，日志添加目标群号
2026-6-11 try22: 在 _do_remind 添加 send.text 诊断日志，记录发送结果
2026-6-12 try23: 修复 stream_id 为空问题（优先取 session_id，群聊时通过 chat API 反查）
2026-6-12 try24: 修复时间窗口逻辑（支持跨天）；无差别催睡改为催促发话人而非目标用户；LLM提示词隐藏添加催睡时间；UI文案优化
2026-6-13 try25: 名字出现概率（私聊0.8/无差别0.3，间隔越短越低最小0.01）；新增沉默模式；LLM附带改为催睡时间+当前时间；LLM决定名字前后置
Q：应该在什么时候获取聊天流？A：收到消息的时候（ON_MESSAGE?）
Q：应该在什么地方获取聊天流？A：尝试在@HookHandler或@EventHandler用self.ctx.chat或尝试新的获取方法：
按时间范围查询指定聊天流
messages = await self.ctx.message.get_by_time_in_chat(
    chat_id=stream_id,
    start_time=start_time,
    end_time=end_time,
)
Q：如何获得ID、昵称：A：参考
通过 person API 获取用户信息
person_id = await self.ctx.person.get_id("qq", target_user_id)
person_name = await self.ctx.person.get_value(person_id, "person_name")
nickname = await self.ctx.person.get_value(person_id, "nickname")
Q：[喊你睡觉]LLM调用异常: [E_CAPABILITY_DENIED] 插件 1m.nightmare 未获授权能力: message.get_recent??
A: _manifest.json 中需要添加权限
"""

from maibot_sdk import API, Field, MaiBotPlugin, MessageGateway, PluginConfigBase, PluginContext, Tool, Command, EventHandler, HookHandler, LLMProvider, LLMProviderBase
from maibot_sdk.types import EventType, ToolParameterInfo, ToolParamType, HookMode, HookOrder
from typing import Dict, Optional, ClassVar, List, Any
import asyncio
import random
import time
import datetime
import json
import os
import aiohttp

# ============================================================================
# 多语言化
# ============================================================================
def _schema_i18n(
    *,
    label_en: str,
    label_ja: str,
    hint_en: Optional[str] = None,
    hint_ja: Optional[str] = None,
    placeholder_en: Optional[str] = None,
    placeholder_ja: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    i18n: Dict[str, Dict[str, str]] = {
        "en_US": {"label": label_en},
        "ja_JP": {"label": label_ja},
    }
    if hint_en is not None:
        i18n["en_US"]["hint"] = hint_en
    if hint_ja is not None:
        i18n["ja_JP"]["hint"] = hint_ja
    if placeholder_en is not None:
        i18n["en_US"]["placeholder"] = placeholder_en
    if placeholder_ja is not None:
        i18n["ja_JP"]["placeholder"] = placeholder_ja
    return i18n

# ============================================================================
# WebUI插件控件生成
# ============================================================================
class NightmarePluginSection(PluginConfigBase):
    """插件基本配置。"""
    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0
    enabled: bool = Field(default=False, description="是否启用喊你睡觉插件", json_schema_extra={"label": "开关", "i18n": _schema_i18n(label_en="Enable", label_ja="アダプターを有効化"), "order": 0})
    config_version: str = Field(default="2.0.0", description="配置版本", json_schema_extra={"label": "配置版本", "i18n": _schema_i18n(label_en="Config version", label_ja="設定バージョン", hint_en="Configuration version number.", hint_ja="設定のバージョン番号。"), "order": 1})


class SchedulerConfig(PluginConfigBase):
    """催睡时间设置。"""
    __ui_label__: ClassVar[str] = "催睡时间"
    __ui_order__: ClassVar[int] = 1

    target_user: str = Field(default="", description="催促对象（QQ号、微信号或其他平台用户ID）", json_schema_extra={"label": "催促对象", "hint": "在这里设定催促对象", "placeholder": "请输入用户ID", "i18n": _schema_i18n(label_en="Target user", label_ja="催促対象", hint_en="Set the target user to remind.", hint_ja="催促する対象を設定します。", placeholder_en="Enter user ID", placeholder_ja="ユーザーIDを入力"), "order": 0})
    test_user: str = Field(default="WebUI用户", description="用于从webUI测试", json_schema_extra={"label": "webui聊天用户名", "hint": "用户名位于webui聊天室左下角", "i18n": _schema_i18n(label_en="WebUI chat username", label_ja="WebUIチャットユーザー名", hint_en="For testing only.", hint_ja="テスト専用。"), "placeholder": "WebUI用户", "order": 0})
    webui_only_commands: bool = Field(default=True, description="是否只有WebUI聊天可以触发 /night 和 /nightmare 命令", json_schema_extra={"label": "命令仅限WebUI", "hint": "开启后命令仅在WebUI聊天中可用", "i18n": _schema_i18n(label_en="Commands only in WebUI", label_ja="コマンドはWebUIのみ"), "order": 1})
    start_time: str = Field(default="22:00", pattern=r"^([01]\d|2[0-3]):([0-5]\d)$", description="催睡开始时间（格式 HH:MM，例如 22:00）", json_schema_extra={"label": "开始时间", "placeholder": "22:00", "i18n": _schema_i18n(label_en="Start time", label_ja="開始時間"), "order": 2})
    sleep_hours: float = Field(default=8, ge=4, le=12, description="睡眠时长（小时）", json_schema_extra={"label": "睡眠时长（小时）", "hint": "低于这个时间间隔发言会被继续催促", "x-widget": "slider", "min": 4, "max": 12, "step": 0.5, "i18n": _schema_i18n(label_en="Sleep hours", label_ja="睡眠時間"), "order": 3})
    silent_mode: bool = Field(default=False, description="沉默模式：开启后拦截消息但不发送任何内容", json_schema_extra={"label": "沉默模式", "hint": "沉默...是最好的陪伴", "i18n": _schema_i18n(label_en="Silent Mode", label_ja="サイレントモード", hint_en="Silence... is the best company.", hint_ja="沈黙...は最高の仲間です。"), "order": 4})


class ReminderConfig(PluginConfigBase):
    """提醒频率与重复设置。"""
    __ui_label__: ClassVar[str] = "提醒设置"
    __ui_order__: ClassVar[int] = 2

    interval_seconds: int = Field(default=30, ge=5, le=120, description="两次催睡之间的最小间隔（秒）", json_schema_extra={"label": "提醒间隔（秒）", "hint": "默认30秒，防止短时间内重复催睡", "i18n": _schema_i18n(label_en="Interval (seconds)", label_ja="間隔（秒）"), "order": 0})
    remind_probability: float = Field(default=1.0, ge=0.0, le=1.0, description="催睡概率", json_schema_extra={"label": "催睡概率", "hint": "满足条件后实际发送的概率", "x-widget": "slider", "min": 0, "max": 1, "step": 0.01, "i18n": _schema_i18n(label_en="Remind probability", label_ja="リマインド確率"), "order": 1})


class LLMConfig(PluginConfigBase):
    """LLM提示词设置（独立提供商）"""
    __ui_label__: ClassVar[str] = "LLM提示词设置"
    __ui_order__: ClassVar[int] = 3

    enable_llm: bool = Field(default=True, description="是否启用LLM", json_schema_extra={"label": "是否启用LLM", "i18n": _schema_i18n(label_en="Enable LLM", label_ja="LLMを有効にする"), "order": 0})
    llm_text: str = Field(default="请根据当前上下文生成一句催促某人去睡觉的话", description="LLM提示词", json_schema_extra={"label": "LLM提示词", "hint": "默认：请根据当前上下文生成一句催促某人去睡觉的话", "i18n": _schema_i18n(label_en="LLM prompt", label_ja="LLMプロンプト"), "order": 1})
    api_base: str = Field(default="https://api.deepseek.com", description="API 地址", json_schema_extra={"label": "API 地址", "placeholder": "https://api.deepseek.com", "i18n": _schema_i18n(label_en="API Base URL", label_ja="APIベースURL"), "order": 2})
    api_key: str = Field(default="", description="API 密钥", json_schema_extra={"label": "API 密钥", "placeholder": "sk-...", "i18n": _schema_i18n(label_en="API Key", label_ja="APIキー"), "order": 3})
    model_name: str = Field(default="deepseek-chat", description="模型名称", json_schema_extra={"label": "模型名称", "placeholder": "deepseek-chat", "i18n": _schema_i18n(label_en="Model Name", label_ja="モデル名"), "order": 4})
    temperature: float = Field(default=0.8, ge=0.0, le=2.0, description="生成温度", json_schema_extra={"label": "温度 (Temperature)", "x-widget": "slider", "min": 0.0, "max": 2.0, "step": 0.1, "i18n": _schema_i18n(label_en="Temperature", label_ja="温度"), "order": 5})


class DefualtGoodNightConfig(PluginConfigBase):
    """默认晚安设置。"""
    __ui_label__: ClassVar[str] = "默认晚安设置"
    __ui_order__: ClassVar[int] = 4
    default_good_night: str = Field(default="睡吧", description="喊你睡觉", json_schema_extra={"label": "默认晚安", "hint": "睡吧", "i18n": _schema_i18n(label_en="Default good night", label_ja="デフォルトの夜寝"), "order": 0})


class JamReminderConfig(PluginConfigBase):
    """无差别催睡配置"""
    __ui_label__: ClassVar[str] = "无差别催睡"
    __ui_order__: ClassVar[int] = 5

    enable_jam_reminder: bool = Field(default=False, description="是否启用无差别催睡", json_schema_extra={"label": "启用无差别催睡", "hint": "开启后，任何人发消息都会被催睡（白名单除外）", "i18n": _schema_i18n(label_en="Enable Jam Reminder", label_ja="無差別催促を有効にする"), "order": 0})
    whitelist: List[str] = Field(default_factory=list, description="免催用户白名单", json_schema_extra={"label": "用户白名单（免催）", "hint": "列表中的用户不会被催促", "i18n": _schema_i18n(label_en="User Whitelist (Exempt)", label_ja="ユーザーホワイトリスト（免除）", placeholder_en="Enter user ID", placeholder_ja="ユーザーIDを入力"), "order": 1, "placeholder": "请输入用户ID"})
    group_whitelist: List[str] = Field(default_factory=list, description="免催群聊白名单", json_schema_extra={"label": "群聊白名单（免催）", "hint": "列表中的群聊不会触发催睡", "i18n": _schema_i18n(label_en="Group Whitelist (Exempt)", label_ja="グループホワイトリスト（免除）", placeholder_en="Enter group ID", placeholder_ja="グループIDを入力"), "order": 2, "placeholder": "输入免催群号"})


class NightmareConfig(PluginConfigBase):
    """配置大纲"""
    plugin: NightmarePluginSection = Field(default_factory=NightmarePluginSection)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    reminder: ReminderConfig = Field(default_factory=ReminderConfig)
    llm_config: LLMConfig = Field(default_factory=LLMConfig)
    default_good_night: DefualtGoodNightConfig = Field(default_factory=DefualtGoodNightConfig)
    jam_reminder: JamReminderConfig = Field(default_factory=JamReminderConfig)


# ============================================================================
# 自定义 LLM Provider
# ============================================================================
class NightmareLLMProvider(LLMProviderBase):
    def __init__(self, plugin: 'NightmarePlugin'):
        self.plugin = plugin

    async def get_response(self, request: dict[str, Any]) -> dict[str, Any]:
        config = self.plugin.config.llm_config
        if not config.api_base or not config.api_key or not config.model_name:
            raise RuntimeError("LLM 提供商配置不完整")
        base = config.api_base.rstrip("/")
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        messages = request.get("message_list")
        if not messages:
            raise ValueError("message_list is required")
        payload = {"model": config.model_name, "messages": messages, "temperature": config.temperature}
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


# ============================================================================
# 插件主体
# ============================================================================
class NightmarePlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已加载")
        self._last_interaction: Dict[str, float] = {}
        self._last_remind: Dict[str, float] = {}
        self._http_session: Optional[aiohttp.ClientSession] = None
        self.provider = NightmareLLMProvider(self)
        self._load_state()

    async def on_unload(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已卸载")
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        self._save_state()

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("[喊你睡觉]插件配置已更新: version=%s", version)

    config_model = NightmareConfig

    @LLMProvider("1m.nightmare.provider", name="Nightmare LLM Provider", description="喊你睡觉插件自带的 OpenAI 兼容 LLM 提供商")
    async def handle_llm(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        return await self.provider.dispatch(operation, request)

    # ===== 持久化辅助 =====
    def _get_state_file(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "nightmare_state.json")

    def _load_state(self) -> None:
        path = self._get_state_file()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._last_interaction = data.get("last_interaction", {})
                self._last_remind = data.get("last_remind", {})
                self.ctx.logger.info("[喊你睡觉] 已从文件恢复催睡状态")
            except Exception as e:
                self.ctx.logger.warning(f"[喊你睡觉] 加载状态文件失败: {e}")

    def _save_state(self) -> None:
        path = self._get_state_file()
        try:
            data = {"last_interaction": self._last_interaction, "last_remind": self._last_remind}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.ctx.logger.warning(f"[喊你睡觉] 保存状态文件失败: {e}")

    # ===== 辅助方法 =====
    def _enabled(self) -> bool:
        try:
            return bool(self.config.plugin.enabled)
        except Exception:
            return False

    def _get_user_id(self, message: dict) -> str:
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            user_info = message_info.get("user_info", {})
            if isinstance(user_info, dict):
                uid = user_info.get("user_id", "")
                if uid: return str(uid)
        user_info = message.get("user_info", {})
        if isinstance(user_info, dict):
            uid = user_info.get("user_id", "")
            if uid: return str(uid)
        sender = message.get("sender", {})
        if isinstance(sender, dict):
            uid = sender.get("user_id", "")
            if uid: return str(uid)
        uid = message.get("user_id", "")
        if uid: return str(uid)
        raw = message.get("raw_message", {})
        if isinstance(raw, dict):
            sender = raw.get("sender", {})
            if isinstance(sender, dict):
                uid = sender.get("user_id", "")
                if uid: return str(uid)
            uid = raw.get("user_id", "")
            if uid: return str(uid)
        return ""

    def _get_group_id(self, message: dict) -> str:
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            group_info = message_info.get("group_info", {})
            if isinstance(group_info, dict):
                gid = group_info.get("group_id", "")
                if gid: return str(gid)
        gid = message.get("group_id", "")
        if gid: return str(gid)
        return ""

    def _get_platform(self, message: dict) -> str:
        platform = message.get("platform", "")
        if platform: return platform
        user_info = message.get("user_info", {})
        platform = user_info.get("platform", "")
        if platform: return platform
        message_info = message.get("message_info", {})
        platform = message_info.get("platform", "")
        if platform: return platform
        return "unknown"

    async def _get_user_name(self, message: dict, user_id: str = "", platform: str = "") -> str:
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            user_info = message_info.get("user_info", {})
            if isinstance(user_info, dict):
                name = user_info.get("user_nickname") or user_info.get("nickname") or user_info.get("user_cardname") or user_info.get("user_name")
                if name: return str(name)
        user_info = message.get("user_info", {})
        if isinstance(user_info, dict):
            name = user_info.get("user_nickname") or user_info.get("nickname") or user_info.get("user_name") or user_info.get("person_name")
            if name: return str(name)
        sender = message.get("sender", {})
        if isinstance(sender, dict):
            name = sender.get("user_nickname") or sender.get("nickname") or sender.get("user_name") or sender.get("sender_name")
            if name: return str(name)
        name = message.get("user_nickname") or message.get("user_name") or message.get("sender_name")
        if name: return str(name)
        raw = message.get("raw_message", {})
        if isinstance(raw, dict):
            sender = raw.get("sender", {})
            if isinstance(sender, dict):
                name = sender.get("user_nickname") or sender.get("nickname") or sender.get("card") or sender.get("user_name")
                if name: return str(name)
        try:
            person_id = await self.ctx.person.get_id(platform, user_id)
            if person_id:
                nickname = await self.ctx.person.get_value(person_id, "nickname")
                if nickname: return str(nickname)
                person_name = await self.ctx.person.get_value(person_id, "person_name")
                if person_name: return str(person_name)
        except Exception:
            pass
        return "小伙伴"

    def _is_inside_remind_window(self, now: datetime.datetime) -> bool:
        try:
            config = self.config
            start_parts = config.scheduler.start_time.split(":")
            start_h = int(start_parts[0])
            start_m = int(start_parts[1])
            start_total = start_h * 60 + start_m
            end_total = (start_total + int(config.scheduler.sleep_hours * 60)) % (24 * 60)
            current_total = now.hour * 60 + now.minute
            if start_total <= end_total:
                return start_total <= current_total <= end_total
            else:
                return current_total >= start_total or current_total <= end_total
        except Exception:
            return False

    def _is_target_user(self, user_id: str) -> bool:
        try:
            config = self.config
            if config.jam_reminder.enable_jam_reminder:
                whitelist = config.jam_reminder.whitelist or []
                return user_id not in whitelist
            else:
                target = config.scheduler.target_user
                if not target:
                    return False
                return user_id == target
        except Exception:
            return False

    def _is_target_group(self, group_id: str) -> bool:
        if not group_id:
            return True
        config = self.config
        if not config.jam_reminder.enable_jam_reminder:
            return True
        group_whitelist = config.jam_reminder.group_whitelist or []
        if not group_whitelist:
            return True
        return group_id not in group_whitelist

    def _is_user_active(self, user_id: str) -> bool:
        last_interact = self._last_interaction.get(user_id, 0)
        if last_interact == 0:
            return False
        sleep_seconds = self.config.scheduler.sleep_hours * 3600
        return (time.time() - last_interact) <= sleep_seconds

    def _min_remind_interval_passed(self, user_id: str) -> bool:
        last_remind = self._last_remind.get(user_id, 0)
        if last_remind == 0:
            return True
        return (time.time() - last_remind) >= self.config.reminder.interval_seconds

    def _roll_probability(self) -> bool:
        prob = self.config.reminder.remind_probability
        if prob >= 1.0: return True
        if prob <= 0.0: return False
        return random.random() < prob

    def _get_name_probability(self, is_private: bool, user_id: str) -> float:
        """
        名字出现概率：
        - 私聊: 基础 0.8
        - 群聊(无差别): 基础 0.3
        - 间隔越短越低: min = 0.01
        最终概率 = max(base - interval_penalty, 0.01)
        """
        base = 0.8 if is_private else 0.3
        last_remind = self._last_remind.get(user_id, 0)
        if last_remind == 0:
            return base
        elapsed = time.time() - last_remind
        interval = self.config.reminder.interval_seconds
        penalty = max(0.0, (1.0 - elapsed / interval)) * (base - 0.01)
        return max(base - penalty, 0.01)

    async def _resolve_stream_id(self, message: dict, group_id: str) -> str:
        stream_id = message.get("stream_id") or message.get("session_id") or ""
        if stream_id:
            return stream_id
        if group_id:
            try:
                stream = await self.ctx.chat.get_stream_by_group_id(group_id, platform="qq")
                if isinstance(stream, dict):
                    stream_id = stream.get("stream_id") or stream.get("session_id") or ""
            except Exception:
                pass
        return stream_id

    # ===== 催睡执行 =====
    async def _do_remind(self, stream_id: str, user_name: str, platform: str, user_id: str, group_id: str = "", is_private: bool = False) -> None:
        config = self.config
        goodnight_text = config.default_good_night.default_good_night
        llm_model_used = "default"

        if config.llm_config.enable_llm:
            try:
                messages = await self.ctx.message.get_recent(chat_id=stream_id, limit=10)
                context_lines = []
                if messages and isinstance(messages, list):
                    for msg in messages[-5:]:
                        if not isinstance(msg, dict): continue
                        sender = msg.get("user_nickname") or msg.get("user_name") or msg.get("sender_name") or msg.get("user_id", "?")
                        text = msg.get("processed_plain_text") or msg.get("raw_message") or msg.get("content") or ""
                        if text and isinstance(text, str):
                            context_lines.append(f"{sender}: {text}")
                context = "\n".join(context_lines) if context_lines else "（暂无聊天记录）"
                now = datetime.datetime.now()
                # 计算名字出现概率
                name_prob = self._get_name_probability(is_private, user_id)
                prompt = (f"{config.llm_config.llm_text}\n用户昵称：{user_name}\n平台：{platform}\n"
                          f"应该催睡的时间：{config.scheduler.start_time}，现在的时间：{now.strftime('%H:%M:%S')}\n"
                          f"请在生成的催睡语句中，以{name_prob:.0%}的概率包含用户昵称\"{user_name}\"（前置或后置均可，由你决定），"
                          f"以{1-name_prob:.0%}的概率不包含昵称。\n\n最近聊天记录：\n{context}")
                request_data = {"message_list": [{"role": "user", "content": prompt}]}
                response = await self.provider.get_response(request_data)
                goodnight_text = response.get("content", "").strip()
                llm_model_used = config.llm_config.model_name or "custom"
                self.ctx.logger.info(f"[喊你睡觉] 自定义 LLM 生成成功，模型={llm_model_used}")
            except Exception as e:
                self.ctx.logger.warning(f"[喊你睡觉] 自定义 LLM 调用失败，回退默认文本: {e}")

        if not goodnight_text or not goodnight_text.strip():
            goodnight_text = "睡吧"

        # 沉默模式：只记日志不发送
        if config.scheduler.silent_mode:
            now = datetime.datetime.now()
            target_info = f"群{group_id}" if group_id else "私聊"
            self.ctx.logger.info(
                f"[喊你睡觉]:喊你睡觉！ 沉默模式，未发送催睡，时间{now.strftime('%Y-%m-%d %H:%M:%S')}，"
                f"平台{platform}，目标{target_info}，用户{user_name}({user_id})，"
                f"模型={llm_model_used}，来源=silent"
            )
            self._last_remind[user_id] = time.time()
            self._save_state()
            return

        # 正常发送
        self.ctx.logger.info(f"[喊你睡觉] 准备发送: stream_id={stream_id}, text={goodnight_text[:50]}")
        result = await self.ctx.send.text(goodnight_text, stream_id)
        self.ctx.logger.info(f"[喊你睡觉] 发送结果: {result}")

        self._last_remind[user_id] = time.time()
        self._save_state()

        now = datetime.datetime.now()
        source = "custom" if config.llm_config.enable_llm else "default"
        target_info = f"群{group_id}" if group_id else "私聊"
        self.ctx.logger.info(
            f"[喊你睡觉]:喊你睡觉！ 已推送催睡，时间{now.strftime('%Y-%m-%d %H:%M:%S')}，"
            f"平台{platform}，目标{target_info}，用户{user_name}({user_id})，"
            f"模型={llm_model_used}，来源={source}，发送结果={result}，"
            f"聊天内容{goodnight_text[:50]}"
        )

    # ===== Hook =====
    @HookHandler(
        "chat.receive.after_process",
        name="nightmare_reminder",
        description="拦截消息并强制发送催睡",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        timeout_ms=5000,
    )
    async def handle_after_receive(self, message: dict, **kwargs) -> dict | None:
        del kwargs
        if not self._enabled():
            return None

        user_id = self._get_user_id(message)
        if not user_id:
            return None

        self._last_interaction[user_id] = time.time()
        self._save_state()

        now = datetime.datetime.now()
        if not self._is_inside_remind_window(now):
            return None
        if not self._is_target_user(user_id):
            return None

        group_id = self._get_group_id(message)
        if not self._is_target_group(group_id):
            return None
        if not self._is_user_active(user_id):
            return None
        if not self._min_remind_interval_passed(user_id):
            return None
        if not self._roll_probability():
            self.ctx.logger.info(f"[喊你睡觉] 概率判定未通过，跳过催睡。概率={self.config.reminder.remind_probability}")
            return None

        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)
        stream_id = await self._resolve_stream_id(message, group_id)
        if not stream_id:
            self.ctx.logger.warning("[喊你睡觉] 无法解析 stream_id，放弃发送催睡")
            return None

        # 判断是否为私聊
        is_private = not bool(group_id)

        await self._do_remind(stream_id, user_name, platform, user_id, group_id, is_private)

        # 沉默模式下仍然拦截消息
        return {"action": "abort"}

    # ===== 事件处理器 =====
    @EventHandler("get_user_info", description="获取用户信息", event_type=EventType.ON_MESSAGE)
    async def on_user_message(self, message, **kwargs):
        user_id = self._get_user_id(message)
        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)
        self.ctx.logger.info(f"[喊你睡觉] 用户消息: 平台={platform}, 用户={user_name}({user_id})")
        return {"intercepted": False}

    # ===== 命令处理器 =====
    @Command("nightmare", description="手动触发催睡测试", pattern=r"^/nightmare$")
    async def handle_nightmare_test(self, stream_id: str = "", **kwargs):
        message = kwargs.get("message", {})
        platform = self._get_platform(message)
        if self.config.scheduler.webui_only_commands and platform != "webui":
            self.ctx.logger.info(f"[喊你睡觉] /nightmare 命令在非WebUI平台被触发，已忽略。平台={platform}, stream_id={stream_id}")
            return True, "", True
        user_id = self._get_user_id(message)
        user_name = await self._get_user_name(message, user_id, platform)
        group_id = self._get_group_id(message)
        is_private = not bool(group_id)
        await self._do_remind(stream_id, user_name, platform, user_id, group_id, is_private)
        return True, "", True

    @Command("night", description="简单测试命令", pattern=r"^/night$")
    async def handle_nightmare_simple(self, stream_id: str = "", **kwargs):
        message = kwargs.get("message", {})
        platform = self._get_platform(message)
        if self.config.scheduler.webui_only_commands and platform != "webui":
            self.ctx.logger.info(f"[喊你睡觉] /night 命令在非WebUI平台被触发，已忽略。平台={platform}, stream_id={stream_id}")
            return True, "", True
        user_id = self._get_user_id(message)
        user_name = await self._get_user_name(message, user_id, platform)
        group_id = self._get_group_id(message)
        now = datetime.datetime.now()
        remind_message = "晚安"
        await self.ctx.send.text(remind_message, stream_id)
        target_info = f"群{group_id}" if group_id else "私聊"
        self.ctx.logger.info(f"[喊你睡觉]:喊你睡觉！ 已推送催睡，时间{now}，平台{platform}，目标{target_info}，用户{user_name}，模型=N/A，来源=command，聊天内容{remind_message}")
        return True, "", True

    @Command("llmtest", description="测试独立LLM提供商连接", pattern=r"^/llmtest$")
    async def handle_llm_test(self, stream_id: str = "", **kwargs):
        config = self.config.llm_config
        if not config.enable_llm:
            await self.ctx.send.text("❌ LLM 未启用", stream_id)
            return True, "LLM 未启用", 0
        try:
            test_request = {"message_list": [{"role": "user", "content": "请用中文回复'连接成功'，不要加任何其他内容。"}]}
            response = await self.provider.get_response(test_request)
            result = response.get("content", "")
            self.ctx.logger.info(f"[喊你睡觉] LLM 提供商测试成功，返回: {result}")
            await self.ctx.send.text(f"✅ LLM 提供商测试成功，回复: {result}", stream_id)
            return True, "测试成功", 1
        except Exception as e:
            self.ctx.logger.error(f"[喊你睡觉] LLM 提供商测试失败: {e}")
            await self.ctx.send.text(f"❌ LLM 提供商测试失败: {e}", stream_id)
            return True, f"测试失败: {e}", 0

    @Command("echo echo", pattern=r"^/echo\secho\s+(?P<text>.+)$")
    async def handle_echo(self, **kwargs):
        matched = kwargs.get("matched_groups", {})
        text = matched.get("text", "").strip()
        stream_id = kwargs["stream_id"]
        await self.ctx.send.text(text, stream_id)
        return True, text, 1


def create_plugin():
    return NightmarePlugin()

# try25

3.readme.me(项目状态标注必须严格按照格式来，不许自由发挥)
# 喊你睡觉(Nightmare)

## 简介

这是一个到达设定时间点后，无论什么地方，只要你出现了麦麦就会喊你去睡觉的插件。主项目是[maibot](https://github.com/Mai-with-u/MaiBot)。

<br>

## 项目状态

### ✅写完了
### ✅测完了
### 🚧维护中
如有疑问请联系作者[1m]331701160或[Maibot插件开发群]1036092828 	

<br>

## 配置

有人性化的webui设计，请在webui插件市场安装并在管理页面进行配置:

<br>

### 插件设置
- **开关**：启用/禁用插件。

### 催睡时间
- **催促对象**：要催睡的目标用户ID（如QQ号、微信号），留空则不催睡任何人（除非开启无差别模式）。
- **WebUI聊天用户名**：仅用于测试时的显示，默认`WebUI用户`。
- **命令仅限WebUI**：开启后`/night`和`/nightmare`命令只在WebUI聊天中生效，其他平台会静默忽略。
- **开始时间**：每天开始催睡的时间（格式`HH:MM`，如`22:00`）。
- **睡眠时长**：用户被认为"入睡"的静默阈值（4‑12小时），当用户停止发言超过此时长，催睡自动停止。
- **沉默模式**：开启后拦截消息但不发送任何内容，仅在日志中记录。沉默...是最好的陪伴。

### 提醒设置
- **提醒间隔**：两次催睡的最小间隔（秒，5‑120）。间隔越短，用户名出现概率越低。如果觉得太吵，说明该睡觉了。
- **催睡概率**：满足所有条件后，实际发送催睡的概率（0‑1，步进0.01）。

### LLM提示词设置（独立提供商）
- **启用LLM**：是否使用大模型生成催睡语句。
- **LLM提示词**：自定义提示词，默认"请根据当前上下文生成一句催促某人去睡觉的话"。
- **API地址**：OpenAI兼容的API端点，默认`https://api.deepseek.com`。
- **API密钥**：你的API Key。
- **模型名称**：要调用的模型，默认`deepseek-chat`。
- **温度**：控制生成的随机性（0‑2，步进0.1，默认0.8）。

### 默认晚安设置
- **默认晚安文本**：LLM未启用或调用失败时使用的固定文本，默认"睡吧"。

### 无差别催睡
- **启用无差别催睡**：开启后，所有用户（除了白名单）都会被催睡。催睡对象为发话人本人，用户昵称出现概率降低至30%。
- **用户白名单（免催）**：在无差别模式下免受催睡的用户ID列表。
- **群聊白名单（免催）**：列表中的群聊不会触发催睡，留空表示所有群聊均可触发。

<br>

## 命令

| 命令 | 说明 |
|------|------|
| `/nightmare` | 手动触发一次完整的催睡流程（含LLM生成），仅在WebUI可用（若配置了"命令仅限WebUI"）。返回空响应，不会干扰主对话。 |
| `/night` | 简单测试命令，发送固定晚安消息"晚安"，同样受WebUI限制。 |
| `/llmtest` | 测试独立LLM提供商连接是否正常，发送测试消息并显示回复，**不受WebUI限制**，方便在任何平台调试。 |
| `/echo echo <text>` | 回显消息，用于基础调试（所有平台可用）。 |

> **注意**：`/nightmare` 和 `/night` 命令会**强制触发**催睡，不受时间窗口、概率、活跃度等条件的限制，但依然遵守"命令仅限WebUI"的设置。在非WebUI平台触发时，插件仅记录日志，不会发送任何消息。

<br>

## 工作原理

1. **触发时机**：插件通过 **BLOCKING Hook** 拦截所有聊天流（QQ群/私聊/WebUI等）中的**每条消息**，在满足催睡条件时直接发送催睡消息并阻止原消息进入 Maisaka 循环。
2. **时间窗口检查**：仅当当前时间落在 `start_time` 至 `start_time + sleep_hours` 窗口内时（支持跨天），才进入后续判断。
3. **目标用户判定**：
   - 若开启**无差别催睡**，则用户白名单外的所有用户都会被催睡（催睡对象为发话人本人）。
   - 若未开启，仅对配置的`target_user`进行催睡。
4. **群聊白名单检查**：若设置了群聊白名单（免催），则列表中的群聊不会触发催睡；未设置则所有群聊均可触发。
5. **活跃度时间门（sleep_hours）**：记录用户最后一次发言时间。如果当前时间距离该时间**超过了睡眠时长**，则认为用户已经入睡，**停止继续催睡**；若仍在睡眠时长内，则持续提醒。
6. **最小间隔控制**：两次催睡之间必须间隔至少`reminder.interval_seconds`秒，避免刷屏。
7. **概率判定**：以配置的概率（0～1）随机决定是否真正发送消息。
8. **用户名出现概率**：
   - 私聊：基础概率 80%
   - 群聊（无差别模式）：基础概率 30%
   - 间隔越短，概率越低，最低为 1%
   - 由 LLM 决定名字放在前面还是后面
9. **生成晚安内容**：
   - 若启用了LLM，插件调用**用户自行配置的独立LLM提供商**（OpenAI 兼容 API，默认指向 DeepSeek），结合最近聊天上下文、催睡时间、当前时间等信息生成个性化的催睡语句。
   - 若未启用LLM或调用失败，则使用**默认晚安文本**（如"睡吧"）。
10. **沉默模式**：若开启，Hook 仍然拦截消息，但不发送任何内容，仅在日志中记录"喊你睡觉！"。沉默...是最好的陪伴。
11. **发送并拦截**：通过`self.ctx.send.text`直接发送催睡消息，然后返回`{"action": "abort"}`阻止原消息继续被 Maisaka 处理，避免重复响应。
12. **状态持久化**：用户的互动时间和催睡时间保存在`nightmare_state.json`中，重启不丢失。

<br>

## 测试

在webui建立聊天,发送"/nightmare"触发测试，
如果看到maibot日志显示`[喊你睡觉]:喊你睡觉！ 已推送催睡，时间...，用户...，模型=...，来源=custom`，并收到晚安消息，则说明测试成功。
如果同时安装了晚安睡眠管理插件，会在插件加载时显示`[喊你睡觉]:已读取晚安睡眠管理插件配置，入睡时间...`。

<br>

## 注意

#### 请确保maibot版本为1.0.0或以上,否则webui可能无法正确显示中文插件配置。

#### 兼容晚安睡眠管理插件，会在晚安后继续催睡。如果安装了晚安睡眠管理插件会自动读取已经设定的作息时间。(将于try26实装)

#### 其他语言翻译没有经过仔细审核。

#### 插件重启后不会丢失催睡状态：用户的互动时间和上次催睡时间会保存在 `nightmare_state.json` 文件中，确保催睡间隔和熬夜判定在重启后依然有效。

*现在，请生成看看日志插件.try1
--------------------------------------------------------try2
*补充文档logger — 日志(不要忘了在manifest生成需要的权限)

# 方式一：通过 ctx.logger（名称自动为 plugin.<plugin_id>）
logger = self.ctx.logger
logger.info("插件已启动")
logger.error(f"请求失败: {err}", exc_info=True)

# 方式二：直接用 stdlib logging（同样会被自动传输）
import logging
logger = logging.getLogger(__name__)
logger.warning("配置缺失，使用默认值")

self.ctx.logger 是标准 logging.Logger，名称为 plugin.<plugin_id>。支持所有标准方法：debug()、info()、warning()、error()、critical()。

日志自动转发

Runner 进程中的日志会自动通过 IPC 传输到主进程，无需额外配置。在主进程日志中可以找到插件输出的所有日志。

    注意：旧版的 await self.ctx.logging.info(...) 异步 API 已移除。请改用上述标准 logging 写法。

--------------------------------------------------------try3
你这个不对，注意添加LLM provider的manifest权限和相关@provider字段，参考：
LLMProvider 组件

@LLMProvider 用于声明插件提供新的 LLM Provider client_type。主程序会将该 client_type 注册到 LLM 客户端注册表中，因此现有 LLMService 和模型任务配置不需要改调用方式——只要模型配置里的 api_providers[].client_type 指向插件声明的值，请求就会通过插件 Provider 发起。

双重声明必须一致

LLM Provider 必须同时满足两处声明，缺一不可：

    _manifest.json 顶层 llm_providers 中静态声明 client_type
    插件代码中使用 @LLMProvider("同一个 client_type") 修饰处理方法

Runner 会校验 manifest 与装饰器收集结果完全一致。任意一边漏写、拼写不一致或同一插件内重复声明，插件都会拒绝加载。不同插件声明同一个 client_type 时，冲突双方都会被阻止加载。
装饰器签名

from maibot_sdk import LLMProvider

@LLMProvider(
    client_type: str,          # 客户端类型标识（必填）
    *,
    name: str = "",            # Provider 展示名称
    description: str = "",     # Provider 描述
    version: str = "1.0.0",    # Provider 实现版本
    **metadata,                # 额外元数据
)

参数说明

    client_type str · 必填 — 客户端类型标识，对应模型配置中的 api_providers[].client_type。不能为空
    name str · 默认 "" — Provider 展示名称。留空时使用 client_type
    description str · 默认 "" — Provider 描述信息
    version str · 默认 "1.0.0" — Provider 实现版本号
    **metadata Any — 额外元数据键值对

Manifest 声明

_manifest.json 顶层必须包含 llm_providers 数组，与代码中的 @LLMProvider 一一对应：

{
  "llm_providers": [
    {
      "client_type": "example.provider",
      "name": "Example Provider",
      "description": "示例 LLM Provider",
      "version": "1.0.0"
    }
  ]
}

llm_providers 字段说明

    client_type str · 必填 — Provider 客户端类型，必须与模型配置 api_providers[].client_type 一致
    name str · 默认 "" — Provider 展示名称
    description str · 默认 "" — Provider 描述
    version str · 默认 "1.0.0" — Provider 实现版本

DANGER

不要在 manifest 的 llm_providers 中写 handler_name 或 metadata——处理函数由 @LLMProvider 装饰器自动收集，不需要手动指定。
Operation 类型

处理方法通过 operation 参数区分请求类型。三种 operation 分别对应不同的 LLM 能力：

    response — LLM 文本/工具响应。主要请求字段：message_list、tool_options、max_tokens、temperature、response_format、extra_params、model_info、api_provider。返回字段：content / response、reasoning_content、tool_calls、usage
    embedding — 文本向量化。主要请求字段：embedding_input、extra_params、model_info、api_provider。返回字段：embedding
    audio_transcription — 语音识别。主要请求字段：audio_base64、max_tokens、extra_params、model_info、api_provider。返回字段：content

三种 operation 的请求中都会包含以下公共字段：

    model_info dict — 当前请求的模型信息
    api_provider dict — 当前请求的 API Provider 配置
    extra_params dict — 额外参数

请求与返回字段
处理方法参数

    operation str — 请求类型：response、embedding、audio_transcription
    request dict[str, Any] — Host 序列化后的请求内容

返回值字段

返回值必须是可序列化字典。Host 会识别以下字段并恢复为统一响应：

    content / response str — 文本响应或音频转写文本
    reasoning_content / reasoning str — 推理内容
    embedding list[float] — 嵌入向量
    tool_calls list — 工具调用快照
    usage dict — token 使用量字典
    raw_data dict — 原始响应数据

基本用法
方式一：手动分发（简单场景）

在处理方法内通过 if/elif 判断 operation 类型分别处理：

from typing import Any

from maibot_sdk import LLMProvider, MaiBotPlugin


class MyLLMPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        return None

    async def on_unload(self) -> None:
        return None

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @LLMProvider("my.provider", name="My Provider", description="自定义 LLM Provider")
    async def handle_llm(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        if operation == "response":
            return {"content": "你好，我来自插件 Provider"}
        if operation == "embedding":
            return {"embedding": [0.0, 0.1, 0.2]}
        if operation == "audio_transcription":
            return {"content": "音频转写结果"}
        raise ValueError(f"不支持的 LLM Provider 操作类型: {operation}")


def create_plugin():
    return MyLLMPlugin()

方式二：LLMProviderBase 基类（推荐，逻辑较多时）

继承 LLMProviderBase，将分发逻辑交给基类的 dispatch() 方法。子类只需实现关心的 operation 方法，未实现的方法会抛出 NotImplementedError：

from typing import Any

from maibot_sdk import LLMProvider, LLMProviderBase, MaiBotPlugin


class MyProvider(LLMProviderBase):
    """自定义 Provider，只实现 response 能力。"""

    async def get_response(self, request: dict[str, Any]) -> dict[str, Any]:
        # request 包含 message_list、tool_options、model_info 等
        return {"content": "来自 Provider 类的响应"}


class MyLLMPlugin(MaiBotPlugin):
    def __init__(self) -> None:
        super().__init__()
        self.provider = MyProvider()

    async def on_load(self) -> None:
        return None

    async def on_unload(self) -> None:
        return None

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @LLMProvider("my.provider")
    async def handle_llm(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        return await self.provider.dispatch(operation, request)


def create_plugin():
    return MyLLMPlugin()

LLMProviderBase 提供以下方法供子类覆写：

    get_response() · operation response — 生成文本或多模态响应（抽象方法，必须实现）
    get_embedding() · operation embedding — 生成文本嵌入（默认抛出 NotImplementedError）
    get_audio_transcriptions() · operation audio_transcription — 生成音频转写（默认抛出 NotImplementedError）

TIP

LLMProviderBase 只是推荐基类，不参与注册。真正的注册入口始终是 @LLMProvider 装饰器。
完整示例

下面是一个完整的最小可用插件，包含 manifest 声明和 Python 代码。

_manifest.json：

{
  "id": "com.example.llm-provider",
  "name": "Example LLM Provider",
  "version": "1.0.0",
  "description": "示例 LLM Provider 插件",
  "author": "example",
  "llm_providers": [
    {
      "client_type": "example.provider",
      "name": "Example Provider",
      "description": "示例 LLM Provider",
      "version": "1.0.0"
    }
  ]
}

main.py：

from typing import Any

from maibot_sdk import LLMProvider, LLMProviderBase, MaiBotPlugin


class ExampleProvider(LLMProviderBase):
    """示例 Provider，实现 response 和 embedding 两种能力。"""

    async def get_response(self, request: dict[str, Any]) -> dict[str, Any]:
        model_info = request.get("model_info", {})
        message_list = request.get("message_list", [])
        # 此处接入实际的 LLM API
        return {
            "content": "来自 example.provider 的响应",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    async def get_embedding(self, request: dict[str, Any]) -> dict[str, Any]:
        embedding_input = request.get("embedding_input", "")
        # 此处接入实际的 Embedding API
        return {"embedding": [0.1, 0.2, 0.3]}


class ExampleLLMPlugin(MaiBotPlugin):
    def __init__(self) -> None:
        super().__init__()
        self.provider = ExampleProvider()

    async def on_load(self) -> None:
        self.ctx.logger.info("Example LLM Provider 插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("Example LLM Provider 插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @LLMProvider("example.provider", name="Example Provider", description="示例 LLM Provider")
    async def handle_llm(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        return await self.provider.dispatch(operation, request)


def create_plugin():
    return ExampleLLMPlugin()

卸载与回退

当 Provider 插件卸载、禁用或热重载失败时，Host 会注销该插件拥有的 client_type。此后新请求会按主程序的模型回退策略尝试下一个可用模型。

INFO

插件 Provider 暂不支持 Host 侧自定义流式处理器或响应解析器。

*now，try3，plugin.py&manifest.json

-----------------------------------------------------------

现在，有一个问题：报错：日志文件不存在: logs/maibot.log。请观察maibot的日志到底是如何生成的试试日志

-----------------------------------------------------------

改为：如果截取时间段内有maisaka输出，则触发词"查你后台"会直接提取这段maisaka输出进行输出到聊天流（不经过LLM总结）。请添加相关WEBUI设置和逻辑。

形如：
╭───────────────────────────── MaiSaka 循环 [73] ──────────────────────────────╮
│ 聊天流名称：Ar Live网络博客官方群2.22                                        │
│ 聊天流ID：46a8bc63f6ce273bfb5c7069a6cd90b9                                   │
│ 当前回复频率：0.200（20.0%）                                                 │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：LongCat-2.0                                                    │ │
│ │ 本次请求token消耗：58.5k                                                 │ │
│ │ 状态：未调用工具，已结束本轮思考                                         │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ 结构化记录：logs/maisaka_prompt/planner/qq_group_227288331/178375897 │ │ │
│ │ │ 5209.json 点击打开 JSON 记录                                         │ │ │
│ │ │ 推理详情浏览：http://127.0.0.1:8001/reasoning-process?stage=planner& │ │ │
│ │ │ session=qq_group_227288331&stem=1783758975209 点击跳转到推理页面     │ │ │
│ │ ╰─ 实际发送 847 条消息|消息 843 条|tool 4 条|cache_window 1024->2048  ─╯ │ │
│ │ ╭──────────────────────────── Maisaka 返回 ────────────────────────────╮ │ │
│ │ │ 当前群聊话题围绕电竞比赛讨论，Dre/fire和WM在讨论Lyon狮队的比赛表现， │ │ │
│ │ │ WM说"打野是最硬的"，Dre/fire说"打野是这届msi最强一档的"。人形大魔王  │ │ │
│ │ │ 在发图但无法识别。混色七尚未参与今日群聊，无未回复的@或提问。        │ │ │
│ │ │                                                                      │ │ │
│ │ │ **分析：**                                                           │ │ │
│ │ │ - 群聊状态：话题围绕电竞比赛（MSI、Lyon狮队）                        │ │ │
│ │ │ - 当前内容：Dre/fire和WM讨论Lyon狮队比赛表现、打野选手               │ │ │
│ │ │ - 混色七参与度：未参与今日对话                                       │ │ │
│ │ │ - 切入难度：话题围绕电竞比赛，已有固定对话者                         │ │ │
│ │ │                                                                      │ │ │
│ │ │ **决策：**                                                           │ │ │
│ │ │ 暂不发言。电竞比赛话题较为具体，Dre/fire和WM已经在讨论，混色七未参与 │ │ │
│ │ │ 该话题。继续观察群聊动态，等待更合适的话题出现。                     │ │ │
│ │ │                                                                      │ │ │
│ │ │ 关于系统提醒的工具（bye_greeting、compare_numbers、hello_greeting）  │ │ │
│ │ │ ，当前场景暂无需求，无需调用。                                       │ │ │
│ │ │                                                                      │ │ │
│ │ │ 关于人物画像信息，人形大魔王"做不到拒绝女色"这一背景信息与当前对话无 │ │ │
│ │ │ 关，不需要使用。                                                     │ │ │
│ │ │                                                                      │ │ │
│ │ │ finish()                                                             │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰─ 流程耗时：Planner 13.51 s | visual_refresh 0.06 s | mid_term_memory_recall ─╯
是maisaka输出，请在收到查你后台命令后整理距离现在最近时间的maisaka输出，并回发。

-----------------------------------------------------------

1. list报错：'list' object has no attribute 'get'
2. 查你后台功能改为仅提取最近的"Maisaka 返回"，整理格式去除额外的框以后进行输出。
3. 不要在webui添加额外Maisaka关键词，删除相关内容。
4. 请将"查你后台"提示词加回webui。

-----------------------------------------------------------

请阅读https://docs.mai-mai.org/plugin/api-reference#logger 或 https://docs.mai-mai.org/plugin/，检查日志项目的实时日志获取逻辑。另外，我已经开启Nas的maibot data/MaiMBot文件夹同步，可以检查这个目录里的日志。

-----------------------------------------------------------

怒了，已经过了11分钟了，难道.log文件还没有更新吗？就不能通过WebSocketLogHandler获取吗？

-----------------------------------------------------------

我所有的文件已经同步到D:\VS Work Space\MaiMBot里了，是实时更新的，请检查

-----------------------------------------------------------

我找到了，maisaka_prompt，maisaka的日志应该是在这个文件里，请检查

-----------------------------------------------------------

另外，这个目录应该是包含所有的聊天流，请注意获取当前的聊天流并按聊天流所在的文件夹读取，现在是这样吗？请综合现在的获取逻辑，将实时的maisaka返回也加入插件的日志小窥功能里。如果开启了LLM，一起发送给LLM进行总结。