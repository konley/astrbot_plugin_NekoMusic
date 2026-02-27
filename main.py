import asyncio
import io
import os
import textwrap
from typing import Dict, List, Tuple

import aiohttp
from PIL import Image, ImageDraw, ImageFont
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp


class MusicSearchDrawer:
    """音乐搜索结果图片绘制器"""

    # 常量定义
    FONT_PATHS = [
        FONT_PATH_REGULAR := os.path.join(os.path.dirname(__file__), "DreamHanSans-W17.ttc"),
        FONT_PATH_BOLD := FONT_PATH_REGULAR,
    ]

    # 颜色定义
    COLOR_BG_START = (248, 250, 255)
    COLOR_BG_END = (255, 252, 248)
    COLOR_HEADER = (0, 40, 100)
    COLOR_SUBTITLE = (80, 80, 80)
    COLOR_SONG_NAME = (0, 60, 130)
    COLOR_SONG_INFO = (70, 70, 70)
    COLOR_CARD_BG = (255, 255, 255)
    COLOR_CARD_OUTLINE = (220, 225, 235)
    COLOR_ACCENT = (0, 90, 180)
    COLOR_FOOTER = (100, 100, 100)

    # 布局尺寸
    # Telegram 图片限制: 宽度最大 1280px, 高度最大 2560px, 大小最大 10MB
    # 使用较小的宽度以确保兼容性和快速加载
    IMG_WIDTH = 700  # 从 800 调整为 700,更适合移动端和 Telegram
    PADDING = 20     # 从 25 调整为 20
    HEADER_HEIGHT = 90  # 从 100 调整为 90
    ITEM_HEIGHT = 110   # 从 120 调整为 110
    FOOTER_HEIGHT = 60

    def __init__(self):
        self._load_fonts()

    def _load_fonts(self):
        """加载字体"""
        import os
        try:
            loaded = False
            for font_path in self.FONT_PATHS:
                # 检查文件是否存在
                if not os.path.exists(font_path):
                    logger.warning(f"字体文件不存在: {font_path}")
                    continue

                # 检查文件是否可读
                if not os.access(font_path, os.R_OK):
                    logger.warning(f"字体文件不可读: {font_path}")
                    continue

                logger.info(f"字体文件存在且可读: {font_path}")

                try:
                    logger.info(f"尝试加载字体: {font_path}")

                    # 尝试多种加载方式
                    # 方式1: 指定索引加载 TTC 字体
                    try:
                        self.font_title = ImageFont.truetype(font_path, 36, index=0)
                        self.font_subtitle = ImageFont.truetype(font_path, 18, index=0)
                        self.font_song_name = ImageFont.truetype(font_path, 22, index=0)
                        self.font_song_info = ImageFont.truetype(font_path, 16, index=0)
                        self.font_footer = ImageFont.truetype(font_path, 12, index=0)
                        logger.info(f"成功加载字体（方式1）: {font_path}")
                        loaded = True
                        break
                    except Exception as e1:
                        logger.warning(f"方式1加载失败 {font_path}: {str(e1)}")
                        pass

                    # 方式2: 不指定索引
                    try:
                        self.font_title = ImageFont.truetype(font_path, 36)
                        self.font_subtitle = ImageFont.truetype(font_path, 18)
                        self.font_song_name = ImageFont.truetype(font_path, 22)
                        self.font_song_info = ImageFont.truetype(font_path, 16)
                        self.font_footer = ImageFont.truetype(font_path, 12)
                        logger.info(f"成功加载字体（方式2）: {font_path}")
                        loaded = True
                        break
                    except Exception as e2:
                        logger.warning(f"方式2加载失败 {font_path}: {str(e2)}")
                        pass

                except Exception as e:
                    logger.warning(f"加载字体 {font_path} 失败: {str(e)}")
                    import traceback
                    logger.warning(traceback.format_exc())
                    continue

            if not loaded:
                logger.warning("所有自定义字体加载失败，使用默认字体（中文可能无法正常显示）")
                self.font_title = ImageFont.load_default()
                self.font_subtitle = ImageFont.load_default()
                self.font_song_name = ImageFont.load_default()
                self.font_song_info = ImageFont.load_default()
                self.font_footer = ImageFont.load_default()
        except Exception as e:
            logger.error(f"字体加载过程发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.font_title = ImageFont.load_default()
            self.font_subtitle = ImageFont.load_default()
            self.font_song_name = ImageFont.load_default()
            self.font_song_info = ImageFont.load_default()
            self.font_footer = ImageFont.load_default()

    @staticmethod
    def _draw_gradient(draw, width: int, height: int, start: Tuple[int, int, int], end: Tuple[int, int, int]):
        """绘制渐变背景"""
        for y in range(height):
            r = int(start[0] + (end[0] - start[0]) * y / height)
            g = int(start[1] + (end[1] - start[1]) * y / height)
            b = int(start[2] + (end[2] - start[2]) * y / height)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

    @staticmethod
    def _draw_rounded_rectangle(draw, xy, radius, fill=None, outline=None, width=1):
        """绘制圆角矩形"""
        x1, y1, x2, y2 = xy
        if x1 >= x2 or y1 >= y2:
            return
        radius = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)

        if fill:
            draw.rectangle((x1 + radius, y1, x2 - radius, y2), fill=fill)
            draw.rectangle((x1, y1 + radius, x2, y2 - radius), fill=fill)
            draw.pieslice((x1, y1, x1 + 2 * radius, y1 + 2 * radius), 180, 270, fill=fill)
            draw.pieslice((x2 - 2 * radius, y1, x2, y1 + 2 * radius), 270, 360, fill=fill)
            draw.pieslice((x1, y2 - 2 * radius, x1 + 2 * radius, y2), 90, 180, fill=fill)
            draw.pieslice((x2 - 2 * radius, y2 - 2 * radius, x2, y2), 0, 90, fill=fill)

        if outline and width > 0:
            draw.arc((x1, y1, x1 + 2 * radius, y1 + 2 * radius), 180, 270, fill=outline, width=width)
            draw.arc((x2 - 2 * radius, y1, x2, y1 + 2 * radius), 270, 360, fill=outline, width=width)
            draw.arc((x1, y2 - 2 * radius, x1 + 2 * radius, y2), 90, 180, fill=outline, width=width)
            draw.arc((x2 - 2 * radius, y2 - 2 * radius, x2, y2), 0, 90, fill=outline, width=width)
            draw.line([(x1 + radius, y1), (x2 - radius, y1)], fill=outline, width=width)
            draw.line([(x1 + radius, y2), (x2 - radius, y2)], fill=outline, width=width)
            draw.line([(x1, y1 + radius), (x1, y2 - radius)], fill=outline, width=width)
            draw.line([(x2, y1 + radius), (x2, y2 - radius)], fill=outline, width=width)

    async def draw_search_result(self, keyword: str, result_data: dict, session) -> bytes:
        """绘制搜索结果图片"""
        try:
            songs = result_data.get("songs", [])
            total = result_data.get("total", 0)

            # 计算总高度
            total_height = self.HEADER_HEIGHT + len(songs) * self.ITEM_HEIGHT + self.FOOTER_HEIGHT + self.PADDING * 3

            # 创建图片
            img = Image.new('RGB', (self.IMG_WIDTH, total_height), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)

            # 绘制渐变背景
            self._draw_gradient(draw, self.IMG_WIDTH, total_height, self.COLOR_BG_START, self.COLOR_BG_END)

            # 绘制顶部装饰条
            draw.rectangle([(0, 0), (self.IMG_WIDTH, 8)], fill=self.COLOR_ACCENT)

            # 绘制标题
            title_text = "音乐搜索"
            draw.text((self.PADDING, 25), title_text, font=self.font_title, fill=self.COLOR_HEADER)

            # 绘制关键词和结果数
            keyword_text = f"关键词: {keyword}"
            keyword_bbox = draw.textbbox((0, 0), keyword_text, font=self.font_subtitle)
            keyword_width = keyword_bbox[2] - keyword_bbox[0]
            draw.text((self.IMG_WIDTH - self.PADDING - keyword_width, 32), keyword_text,
                     font=self.font_subtitle, fill=self.COLOR_SUBTITLE)

            result_text = f"共找到 {total} 首歌曲"
            draw.text((self.PADDING, 70), result_text, font=self.font_subtitle, fill=self.COLOR_SUBTITLE)

            # 绘制分割线
            draw.line([(self.PADDING, self.HEADER_HEIGHT - 5), (self.IMG_WIDTH - self.PADDING, self.HEADER_HEIGHT - 5)],
                     fill=(200, 200, 200), width=2)

            # 绘制每首歌曲
            y_offset = self.HEADER_HEIGHT
            for idx, song_info in enumerate(songs, 1):
                # 绘制卡片背景（交替颜色）
                card_bg = self.COLOR_CARD_BG if idx % 2 == 1 else (248, 250, 255)
                self._draw_rounded_rectangle(
                    draw,
                    (self.PADDING, y_offset + 5, self.IMG_WIDTH - self.PADDING, y_offset + self.ITEM_HEIGHT - 5),
                    radius=10,
                    fill=card_bg,
                    outline=self.COLOR_CARD_OUTLINE,
                    width=1
                )

                # 绘制序号
                draw.text((self.PADDING + 15, y_offset + 15), str(idx),
                         font=self.font_song_name, fill=self.COLOR_ACCENT)

                # 下载封面图片
                cover_url = song_info.get("cover_url")
                if cover_url:
                    try:
                        async with session.get(cover_url, timeout=8) as cover_response:
                            if cover_response.status == 200:
                                cover_data = await cover_response.read()
                                cover_img = Image.open(io.BytesIO(cover_data))
                                cover_img = cover_img.resize((100, 100), Image.Resampling.LANCZOS)
                                img.paste(cover_img, (self.PADDING + 55, y_offset + 10))
                    except Exception as e:
                        logger.error(f"下载封面失败: {str(e)}")

                # 解析歌曲信息
                text_lines = song_info.get("text", "").split('\n')
                line_y = y_offset + 15
                text_x = self.PADDING + 180

                for line_idx, line in enumerate(text_lines):
                    if line_idx == 0:  # 歌曲名
                        draw.text((text_x, line_y), line, font=self.font_song_name, fill=self.COLOR_SONG_NAME)
                    else:  # 其他信息
                        draw.text((text_x, line_y), line, font=self.font_song_info, fill=self.COLOR_SONG_INFO)
                    line_y += 24

                y_offset += self.ITEM_HEIGHT

            # 绘制底部版权（两行）
            footer_text1 = "Neko云音乐 - Powered by 不穿胖次の小奶猫"
            footer_text2 = "music.cnmsb.xin 蜀ICP备2025177767号-1"

            # 第一行
            footer_bbox1 = draw.textbbox((0, 0), footer_text1, font=self.font_footer)
            footer_width1 = footer_bbox1[2] - footer_bbox1[0]
            footer_x1 = (self.IMG_WIDTH - footer_width1) // 2
            draw.text((footer_x1, total_height - self.FOOTER_HEIGHT + 8), footer_text1,
                     font=self.font_footer, fill=self.COLOR_FOOTER)

            # 第二行
            footer_bbox2 = draw.textbbox((0, 0), footer_text2, font=self.font_footer)
            footer_width2 = footer_bbox2[2] - footer_bbox2[0]
            footer_x2 = (self.IMG_WIDTH - footer_width2) // 2
            draw.text((footer_x2, total_height - self.FOOTER_HEIGHT + 26), footer_text2,
                     font=self.font_footer, fill=self.COLOR_FOOTER)

            # 转换为 bytes
            with io.BytesIO() as output:
                img.save(output, format='PNG', optimize=True)
                return output.getvalue()

        except Exception as e:
            logger.error(f"绘制搜索结果图片失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None


@register("nekomusic", "NyaNyagulugulu", "Neko云音乐点歌插件", "1.7.0", "https://github.com/NyaNyagulugulu/astrbot_NekoMusic")
class Main(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.drawer = MusicSearchDrawer()
        # 存储每个会话的搜索结果，格式: {session_id: {"songs": [...], "timestamp": ...}}
        self.search_results = {}

    @filter.regex(r"^点歌.*")
    async def search_music(self, event: AstrMessageEvent):
        """搜索音乐"""
        msg_text = event.message_str
        keyword = msg_text[2:].strip()

        if not keyword:
            yield event.plain_result("请输入要搜索的歌曲名称,例如:点歌 Lemon")
            return

        api_url = "https://music.cnmsb.xin/api/music/search"
        json_data = {"query": keyword}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=json_data, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        result_data = self.handle_search_result(data)

                        # 保存搜索结果到会话
                        session_id = event.session_id
                        self.search_results[session_id] = {
                            "songs": data.get("results", [])
                        }

                        # 使用 drawer 绘制图片
                        image_bytes = await self.drawer.draw_search_result(keyword, result_data, session)

                        if image_bytes:
                            # 获取当前平台
                            platform = self._get_platform(event)
                            
                            # 构建提示文本
                            if platform == 'telegram':
                                hint_text = f"🎵 搜索结果: {keyword}\n共找到 {result_data.get('total', 0)} 首歌曲\n💡 点击回复按钮并输入序号即可播放"
                            else:
                                hint_text = f"🎵 搜索结果: {keyword}\n共找到 {result_data.get('total', 0)} 首歌曲\n💡 回复序号即可播放,例如: 1"
                            
                            yield event.chain_result([
                                Comp.Plain(hint_text),
                                Comp.Image.fromBytes(image_bytes)
                            ])
                        else:
                            yield event.plain_result("图片生成失败，请稍后重试")
                    else:
                        yield event.plain_result(f"搜索失败,API 返回状态码: {response.status}")
        except Exception as e:
            logger.error(f"搜索音乐时发生错误: {str(e)}")
            yield event.plain_result(f"搜索失败: {str(e)}")

    def handle_search_result(self, data: dict) -> dict:
        """处理搜索结果"""
        result = {"songs": [], "total": 0}

        if data.get("success") and data.get("results"):
            songs = data["results"]

            if not songs:
                result["songs"] = [{"cover_url": None, "text": "未找到相关歌曲"}]
                return result

            result["total"] = len(songs)

            # 显示所有歌曲
            for idx, song in enumerate(songs, 1):
                song_name = song.get("name", song.get("title", "未知歌曲"))
                artist = song.get("artist", song.get("singer", song.get("ar", "未知歌手")))
                album = song.get("album", song.get("al", "未知专辑"))
                song_id = song.get("id", "")

                # 打印完整的歌曲数据结构用于调试
                logger.info(f"歌曲 {idx} 数据: {song}")

                # 使用封面 API 获取封面图片
                cover_url = None
                if song_id:
                    cover_url = f"https://music.cnmsb.xin/api/music/cover/{song_id}"

                # 构建歌曲信息文本
                song_text = f"{song_name}\n"
                song_text += f"歌手: {artist}\n"
                song_text += f"专辑: {album}\n"
                if song_id:
                    song_text += f"平台音乐ID: {song_id}"

                result["songs"].append({
                    "cover_url": cover_url,
                    "text": song_text
                })
        else:
            result["songs"] = [{"cover_url": None, "text": f"搜索失败: {data.get('message', '未知错误')}"}]

        return result

    def _get_platform(self, event: AstrMessageEvent) -> str:
        """获取当前平台类型"""
        # 尝试从事件中获取平台信息
        if hasattr(event, 'platform'):
            platform = event.platform
            # 处理 PlatformMetadata 对象
            if hasattr(platform, 'name'):
                return platform.name.lower()
            elif isinstance(platform, str):
                return platform.lower()
        
        # 尝试从 message_obj 中获取
        if hasattr(event, 'message_obj') and hasattr(event.message_obj, 'platform'):
            platform = event.message_obj.platform
            # 处理 PlatformMetadata 对象
            if hasattr(platform, 'name'):
                return platform.name.lower()
            elif isinstance(platform, str):
                return platform.lower()
        
        # 默认返回 qq
        return 'qq'

    @filter.regex(r"^\d+$")
    async def play_music(self, event: AstrMessageEvent):
        """播放音乐（通过序号）"""
        msg_text = event.message_str.strip()

        # 检查是否是纯数字
        if not msg_text.isdigit():
            return

        platform = self._get_platform(event)
        logger.info(f"当前平台: {platform}")

        # 检查是否引用了消息 - 从消息链中查找 Reply 组件
        reply_msg = None
        if hasattr(event, 'message_obj') and hasattr(event.message_obj, 'message'):
            components = event.message_obj.message
            # 遍历消息链查找 Reply 组件
            for comp in components:
                if hasattr(comp, 'type') and comp.type == 'Reply':
                    reply_msg = comp
                    logger.info(f"找到 Reply 组件: {reply_msg}")
                    break

        if not reply_msg:
            logger.info("没有引用消息，跳过播放")
            return

        # 检查引用的消息发送者是否是机器人自己
        # Telegram 平台: sender_id 是数字, bot_id 可能是字符串名称
        # QQ 平台: 两者都是数字字符串
        if hasattr(reply_msg, 'sender_id'):
            reply_sender_id = reply_msg.sender_id
            bot_id = event.get_self_id()
            platform = self._get_platform(event)

            # Telegram 特殊处理: 检查 Reply 组件的 sender_nickname 是否与 bot_id 匹配
            if platform == 'telegram':
                # 在 Telegram 上,bot_id 可能是机器人名称(如 'nekoMcServer_bot')
                # 检查 Reply 组件是否有 sender_nickname 属性
                if hasattr(reply_msg, 'sender_nickname'):
                    reply_sender_name = reply_msg.sender_nickname
                    if str(reply_sender_name) != str(bot_id):
                        logger.info(f"Telegram: 引用消息发送者昵称: {reply_sender_name}, 机器人ID: {bot_id}，不匹配，跳过播放")
                        return
                else:
                    # 如果没有 sender_nickname,尝试其他方式验证
                    logger.info(f"Telegram: Reply 组件缺少 sender_nickname，跳过验证")
            else:
                # QQ 平台或其他平台: 直接比较 ID
                if str(reply_sender_id) != str(bot_id):
                    logger.info(f"引用的消息发送者: {reply_sender_id}, 机器人ID: {bot_id}，不匹配，跳过播放")
                    return
        else:
            logger.info("reply_msg 没有 sender_id 属性，跳过播放")
            return

        index = int(msg_text) - 1  # 转换为 0-based 索引
        logger.info(f"用户输入序号: {msg_text}, 转换后索引: {index}")

        # 获取会话的搜索结果
        session_id = event.session_id
        logger.info(f"会话ID: {session_id}")
        logger.info(f"已保存的搜索结果会话: {list(self.search_results.keys())}")
        
        # 处理 Telegram 的会话 ID (可能包含消息 ID, 如: -1001934802217#27946)
        # 提取群组/聊天 ID 部分（# 之前的部分）
        match_session_id = session_id.split('#')[0] if '#' in session_id else session_id
        logger.info(f"匹配使用的会话ID: {match_session_id}")
        
        # 检查是否有匹配的搜索结果
        if match_session_id in self.search_results:
            search_data = self.search_results[match_session_id]
            songs = search_data["songs"]
            logger.info(f"找到 {len(songs)} 首歌曲")
        elif session_id in self.search_results:
            # 尝试直接匹配（兼容其他平台）
            search_data = self.search_results[session_id]
            songs = search_data["songs"]
            logger.info(f"直接匹配找到 {len(songs)} 首歌曲")
        else:
            # 如果没有搜索结果，不处理（让其他过滤器处理）
            logger.info(f"会话 {session_id} 或 {match_session_id} 没有搜索结果，跳过播放")
            return

        # 检查索引是否有效
        if index < 0 or index >= len(songs):
            yield event.plain_result(f"序号无效，请输入 1-{len(songs)} 之间的数字")
            return

        # 获取歌曲信息
        logger.info(f"准备播放第 {index + 1} 首歌曲")
        song = songs[index]
        song_name = song.get("name", song.get("title", "未知歌曲"))
        song_id = song.get("id", "")

        if not song_id:
            yield event.plain_result("该歌曲没有有效的 ID，无法播放")
            return

        # 生成播放链接
        play_url = f"https://music.cnmsb.xin/detail/{song_id}"
        audio_url = f"https://music.cnmsb.xin/api/music/file/{song_id}"

        # 先返回播放链接
        yield event.chain_result([
            Comp.Plain(f"🎶 Neko云音乐。听见好音乐\n🔗 {play_url}\n🎵 正在发送音乐，请稍后\n平台内均为无损音质，发送可能较慢，请耐心等待..."),
        ])

        # 下载音频并发送语音
        try:
            async with aiohttp.ClientSession() as session:
                logger.info(f"尝试下载音频: {audio_url}")
                async with session.get(audio_url, timeout=60) as audio_response:
                    logger.info(f"音频响应状态码: {audio_response.status}")
                    if audio_response.status == 200:
                        audio_data = await audio_response.read()
                        audio_size_mb = len(audio_data) / (1024 * 1024)
                        logger.info(f"音频数据大小: {len(audio_data)} bytes ({audio_size_mb:.2f} MB)")

                        # 平台限制检查和音频压缩
                        # Telegram: 语音文件最大 50MB
                        # QQ: 语音消息通常限制在 10MB 以内
                        max_size_mb = 50 if platform == 'telegram' else 10
                        
                        # 根据平台选择音频格式
                        # Telegram 支持 MP3, OGG, M4A 等格式
                        # QQ 主要支持 SILK/AMR 格式，但也支持发送音频文件
                        audio_format = '.mp3' if platform == 'telegram' else '.mp3'

                        # 保存为临时文件
                        import tempfile
                        with tempfile.NamedTemporaryFile(delete=False, suffix=audio_format) as temp_file:
                            temp_file.write(audio_data)
                            temp_path = temp_file.name
                        logger.info(f"音频已保存到临时文件: {temp_path}")

                        # 检查文件大小，如果超过限制则压缩
                        temp_file_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
                        logger.info(f"临时文件大小: {temp_file_size_mb:.2f} MB")

                        if temp_file_size_mb > max_size_mb:
                            logger.info(f"文件过大 ({temp_file_size_mb:.2f}MB)，开始压缩...")
                            yield event.plain_result(f"⏳ 文件较大 ({temp_file_size_mb:.2f}MB)，正在压缩中，请稍候...")
                            
                            # 使用 ffmpeg 压缩音频
                            compressed_path = temp_path.replace(audio_format, f'_compressed{audio_format}')
                            try:
                                # 检查 ffmpeg 是否可用
                                import shutil
                                if not shutil.which('ffmpeg'):
                                    logger.error("ffmpeg 未安装，无法压缩音频")
                                    yield event.plain_result(f"❌ 音频文件过大 ({temp_file_size_mb:.2f}MB)，但 ffmpeg 未安装无法压缩\n请直接点击播放链接收听: {play_url}")
                                    os.unlink(temp_path)
                                    return

                                # 使用 ffmpeg 压缩
                                # 目标：降低比特率到 128kbps，采样率到 44100Hz，保留双声道
                                compress_cmd = [
                                    'ffmpeg', '-i', temp_path,
                                    '-b:a', '128k',  # 音频比特率 128kbps
                                    '-ar', '44100',  # 采样率 44100Hz
                                    '-ac', '2',      # 双声道
                                    '-y',            # 覆盖输出文件
                                    compressed_path
                                ]
                                
                                process = await asyncio.create_subprocess_exec(
                                    *compress_cmd,
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE
                                )
                                
                                stdout, stderr = await process.communicate()
                                
                                if process.returncode != 0:
                                    logger.error(f"ffmpeg 压缩失败: {stderr.decode()}")
                                    yield event.plain_result(f"❌ 音频压缩失败，请直接点击播放链接收听: {play_url}")
                                    os.unlink(temp_path)
                                    return
                                
                                # 检查压缩后的大小
                                compressed_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
                                logger.info(f"压缩完成: {temp_file_size_mb:.2f}MB → {compressed_size_mb:.2f}MB")
                                
                                # 删除原文件，使用压缩后的文件
                                os.unlink(temp_path)
                                temp_path = compressed_path
                                
                                # 如果压缩后仍然过大
                                if compressed_size_mb > max_size_mb:
                                    logger.warning(f"压缩后仍然过大 ({compressed_size_mb:.2f}MB)")
                                    yield event.plain_result(f"音频压缩后仍较大 ({compressed_size_mb:.2f}MB)，可能发送失败\n请直接点击播放链接收听: {play_url}")
                                    # 不返回，继续尝试发送
                                else:
                                    #yield event.plain_result(f"压缩完成 ({compressed_size_mb:.2f}MB)，开始发送...")
                                    logger.info(f"压缩完成 ({compressed_size_mb:.2f}MB)，开始发送...")
                                    
                            except Exception as compress_error:
                                logger.error(f"压缩音频时发生错误: {str(compress_error)}")
                                import traceback
                                logger.error(traceback.format_exc())
                                #yield event.plain_result(f"压缩失败，尝试发送原文件\n请直接点击播放链接收听: {play_url}")

                        # 发送语音（使用 Record 组件，传入文件路径）
                        # Record 组件会自动根据平台适配格式
                        logger.info(f"开始发送语音到 {platform} 平台")
                        try:
                            yield event.chain_result([
                                Comp.Record(file=temp_path)
                            ])
                            logger.info("语音发送成功")
                        except Exception as send_error:
                            logger.error(f"发送语音失败: {str(send_error)}")
                            # 如果发送失败，提供备用方案
                            yield event.plain_result(f"⚠️ 语音发送失败，请直接点击播放链接收听: {play_url}")

                        # 清理临时文件
                        try:
                            os.unlink(temp_path)
                            logger.info(f"已清理临时文件: {temp_path}")
                        except Exception as cleanup_error:
                            logger.warning(f"清理临时文件失败: {str(cleanup_error)}")
                    else:
                        response_text = await audio_response.text()
                        logger.error(f"下载音频失败,状态码: {audio_response.status}, 响应: {response_text}")
                        yield event.plain_result(f"❌ 音频下载失败(状态码: {audio_response.status})")
        except asyncio.TimeoutError:
            logger.error("下载音频超时")
            yield event.plain_result(f"❌ 下载音频超时，请直接点击播放链接收听: {play_url}")
        except Exception as e:
            logger.error(f"下载或发送音频时发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            yield event.plain_result(f"❌ 发送音乐失败: {str(e)}\n请直接点击播放链接收听: {play_url}")