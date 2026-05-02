import asyncio
import io
import json
import os
import textwrap
from typing import Dict, List, Tuple

import aiohttp
from PIL import Image, ImageDraw, ImageFont
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
import shutil


class MusicSearchDrawer:
    """音乐搜索结果图片绘制器"""

    # 常量定义
    FONT_PATHS = [
        FONT_PATH_REGULAR := os.path.join(os.path.dirname(__file__), "DreamHanSans-W17.ttc"),
        FONT_PATH_BOLD := FONT_PATH_REGULAR,
    ]

    # 颜色定义 - 二次元风格配色
    COLOR_BG_START = (255, 245, 248)  # 樱花粉渐变起始
    COLOR_BG_END = (245, 248, 255)    # 天空蓝渐变结束
    COLOR_HEADER = (102, 78, 163)     # 梦幻紫
    COLOR_SUBTITLE = (158, 158, 158)  # 柔和灰
    COLOR_SONG_NAME = (68, 68, 68)    # 深灰
    COLOR_SONG_INFO = (142, 142, 142) # 浅灰
    COLOR_CARD_BG = (255, 255, 255)   # 纯白
    COLOR_CARD_OUTLINE = (230, 230, 250) # 淡紫边框
    COLOR_ACCENT = (255, 107, 157)    # 粉色强调色
    COLOR_ACCENT_SECOND = (78, 205, 196) # 青色辅助色
    COLOR_FOOTER = (180, 180, 180)    # 底部文字颜色
    COLOR_NUMBER_BG = (255, 107, 157) # 序号背景粉色
    COLOR_NUMBER_TEXT = (255, 255, 255) # 序号文字白色

    # 布局尺寸
    # Telegram 图片限制: 宽度最大 1280px, 高度最大 2560px, 大小最大 10MB
    # 使用较小的宽度以确保兼容性和快速加载
    IMG_WIDTH = 720  # 优化宽度
    PADDING = 24     # 内边距
    HEADER_HEIGHT = 140  # 标题区域高度（增加）
    ITEM_HEIGHT = 120    # 每首歌曲的高度
    FOOTER_HEIGHT = 60   # 底部高度（减少）

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
        """绘制搜索结果图片 - 二次元风格（使用 PIL）"""
        try:
            songs = result_data.get("songs", [])
            total = result_data.get("total", 0)

            # 检查 songs 是否为 None
            if songs is None:
                logger.error("songs 为 None，无法绘制图片")
                return None

            # 计算总高度
            total_height = self.HEADER_HEIGHT + len(songs) * self.ITEM_HEIGHT + self.FOOTER_HEIGHT + self.PADDING * 3

            # 创建图片
            img = Image.new('RGB', (self.IMG_WIDTH, total_height), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)

            # 绘制渐变背景
            self._draw_gradient(draw, self.IMG_WIDTH, total_height, self.COLOR_BG_START, self.COLOR_BG_END)

            # 绘制顶部装饰条（渐变色）
            self._draw_gradient(draw, self.IMG_WIDTH, 6, self.COLOR_ACCENT, self.COLOR_ACCENT_SECOND)

            # 绘制标题区域背景
            header_bg_y = self.HEADER_HEIGHT - 20
            self._draw_rounded_rectangle(
                draw,
                (self.PADDING - 8, 6, self.IMG_WIDTH - self.PADDING + 8, header_bg_y),
                radius=12,
                fill=(255, 255, 255),
                outline=self.COLOR_CARD_OUTLINE,
                width=1
            )

            # 绘制标题（带阴影效果）
            title_text = "音乐搜索"
            title_bbox = draw.textbbox((0, 0), title_text, font=self.font_title)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (self.IMG_WIDTH - title_width) // 2

            # 阴影
            draw.text((title_x + 2, 28 + 2), title_text, font=self.font_title, fill=(200, 200, 200))
            # 主标题
            draw.text((title_x, 28), title_text, font=self.font_title, fill=self.COLOR_HEADER)

            # 绘制关键词标签
            keyword_label = f"搜索: {keyword}"
            keyword_bbox = draw.textbbox((0, 0), keyword_label, font=self.font_subtitle)
            keyword_width = keyword_bbox[2] - keyword_bbox[0]
            keyword_x = (self.IMG_WIDTH - keyword_width) // 2
            draw.text((keyword_x, 70), keyword_label, font=self.font_subtitle, fill=self.COLOR_ACCENT)

            # 绘制结果数
            result_text = f"找到 {total} 首歌曲"
            result_bbox = draw.textbbox((0, 0), result_text, font=self.font_subtitle)
            result_width = result_bbox[2] - result_bbox[0]
            result_x = (self.IMG_WIDTH - result_width) // 2
            draw.text((result_x, 92), result_text, font=self.font_subtitle, fill=self.COLOR_SUBTITLE)

            # 绘制每首歌曲
            y_offset = self.HEADER_HEIGHT
            for idx, song_info in enumerate(songs, 1):
                # 绘制卡片背景（圆角矩形）
                card_y_start = y_offset + 8
                card_y_end = y_offset + self.ITEM_HEIGHT - 8

                # 卡片阴影
                shadow_offset = 3
                self._draw_rounded_rectangle(
                    draw,
                    (self.PADDING + shadow_offset, card_y_start + shadow_offset,
                     self.IMG_WIDTH - self.PADDING + shadow_offset, card_y_end + shadow_offset),
                    radius=16,
                    fill=(240, 240, 245)
                )

                # 卡片主体
                self._draw_rounded_rectangle(
                    draw,
                    (self.PADDING, card_y_start, self.IMG_WIDTH - self.PADDING, card_y_end),
                    radius=16,
                    fill=self.COLOR_CARD_BG,
                    outline=self.COLOR_CARD_OUTLINE,
                    width=2
                )

                # 绘制序号（圆形背景）
                number_x = self.PADDING + 28
                number_y = y_offset + 52
                number_radius = 20
                draw.ellipse([
                    (number_x - number_radius, number_y - number_radius),
                    (number_x + number_radius, number_y + number_radius)
                ], fill=self.COLOR_NUMBER_BG)

                # 序号文字
                number_bbox = draw.textbbox((0, 0), str(idx), font=self.font_song_name)
                number_w = number_bbox[2] - number_bbox[0]
                number_h = number_bbox[3] - number_bbox[1]
                draw.text((number_x - number_w // 2, number_y - number_h // 2), str(idx),
                         font=self.font_song_name, fill=self.COLOR_NUMBER_TEXT)

                # 下载封面图片
                cover_url = song_info.get("cover_url")
                if cover_url:
                    try:
                        async with session.get(cover_url, timeout=8) as cover_response:
                            if cover_response.status == 200:
                                cover_data = await cover_response.read()
                                cover_img = Image.open(io.BytesIO(cover_data))

                                # 制作圆形封面
                                cover_size = 90
                                mask = Image.new('L', (cover_size, cover_size), 0)
                                draw_mask = ImageDraw.Draw(mask)
                                draw_mask.ellipse([(0, 0), (cover_size, cover_size)], fill=255)

                                cover_img = cover_img.resize((cover_size, cover_size), Image.Resampling.LANCZOS)
                                cover_img.putalpha(mask)

                                # 封面阴影
                                cover_shadow_x = self.PADDING + 70 + 2
                                cover_shadow_y = y_offset + 20 + 2
                                draw.ellipse([
                                    (cover_shadow_x, cover_shadow_y),
                                    (cover_shadow_x + cover_size, cover_shadow_y + cover_size)
                                ], fill=(220, 220, 230))

                                # 封面主体
                                img.paste(cover_img, (self.PADDING + 70, y_offset + 20), cover_img)
                    except Exception as e:
                        logger.error(f"下载封面失败: {str(e)}")

                # 解析歌曲信息
                text_lines = song_info.get("text", "").split('\n')
                line_y = y_offset + 20
                text_x = self.PADDING + 185

                for line_idx, line in enumerate(text_lines):
                    if line_idx == 0:  # 歌曲名
                        draw.text((text_x, line_y), line, font=self.font_song_name, fill=self.COLOR_SONG_NAME)
                        line_y += 24  # 歌曲名后间距
                    else:  # 其他信息（歌手、专辑、ID）
                        draw.text((text_x, line_y), line, font=self.font_song_info, fill=self.COLOR_SONG_INFO)
                        line_y += 20  # 其他信息行间距

                y_offset += self.ITEM_HEIGHT

            # 绘制底部装饰区域
            footer_y_start = total_height - self.FOOTER_HEIGHT - self.PADDING
            self._draw_rounded_rectangle(
                draw,
                (self.PADDING, footer_y_start, self.IMG_WIDTH - self.PADDING, total_height - self.PADDING // 2),
                radius=16,
                fill=(255, 255, 255),
                outline=self.COLOR_CARD_OUTLINE,
                width=1
            )

            # 绘制底部装饰条
            self._draw_gradient(draw, self.IMG_WIDTH - self.PADDING * 2, 4,
                               self.COLOR_ACCENT, self.COLOR_ACCENT_SECOND)
            draw.rectangle([
                (self.PADDING, footer_y_start),
                (self.IMG_WIDTH - self.PADDING, footer_y_start + 4)
            ], fill=self.COLOR_ACCENT)

            # 绘制底部版权（两行）
            footer_text1 = "Neko云音乐 - Powered by 不穿胖次の小奶猫"
            footer_text2 = "music.cnmsb.xin | 蜀ICP备2025177767号-1"

            # 第一行
            footer_bbox1 = draw.textbbox((0, 0), footer_text1, font=self.font_footer)
            footer_width1 = footer_bbox1[2] - footer_bbox1[0]
            footer_x1 = (self.IMG_WIDTH - footer_width1) // 2
            draw.text((footer_x1, footer_y_start + 12), footer_text1,
                     font=self.font_footer, fill=self.COLOR_FOOTER)

            # 第二行
            footer_bbox2 = draw.textbbox((0, 0), footer_text2, font=self.font_footer)
            footer_width2 = footer_bbox2[2] - footer_bbox2[0]
            footer_x2 = (self.IMG_WIDTH - footer_width2) // 2
            draw.text((footer_x2, footer_y_start + 26), footer_text2,
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


@register("nekomusic", "NyaNyagulugulu", "Neko云音乐点歌插件", "1.9.0", "https://github.com/NyaNyagulugulu/astrbot_NekoMusic")
class Main(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.drawer = MusicSearchDrawer()
        # 存储每个消息的搜索结果，格式: {message_id: {"songs": [...], "timestamp": ...}}
        # 使用消息ID而不是session_id，这样同一会话中多次搜索不会互相覆盖
        self.search_results = {}

        # 从配置文件 schema 读取默认值
        schema_path = os.path.join(os.path.dirname(__file__), "_conf_schema.json")
        schema_defaults = {}
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
                for key, value in schema.items():
                    schema_defaults[key] = value.get("default")
        except Exception as e:
            logger.warning(f"读取配置 schema 失败: {e}")

        # 从配置文件读取配置，如果不存在则使用 schema 中的默认值
        self.config = config or {}
        try:
            self.use_local_server = self.config.get("use_local_server", schema_defaults.get("use_local_server", False))
            self.local_server_port = self.config.get("local_server_port", schema_defaults.get("local_server_port", 3000))
        except Exception:
            self.use_local_server = schema_defaults.get("use_local_server", False)
            self.local_server_port = schema_defaults.get("local_server_port", 3000)

        # 设置API基础URL
        if self.use_local_server:
            self.api_base_url = f"http://localhost:{self.local_server_port}"
            logger.info(f"使用本机服务器模式，端口: {self.local_server_port}")
        else:
            self.api_base_url = "https://music.cnmsb.xin"
            logger.info("使用在线服务器模式")

    @filter.regex(r"^点歌.*")
    async def search_music(self, event: AstrMessageEvent):
        """搜索音乐"""
        msg_text = event.message_str
        keyword = msg_text[2:].strip()

        if not keyword:
            yield event.plain_result("请输入要搜索的歌曲名称,例如:点歌 Lemon")
            return

        api_url = f"{self.api_base_url}/api/music/search"
        json_data = {"query": keyword}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=json_data, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        result_data = self.handle_search_result(data)

                        # 获取当前消息的消息ID（用户发送的点歌消息ID）
                        user_message_id = self._get_message_id(event)
                        logger.info(f"搜索音乐，用户消息ID: {user_message_id}")

                        # 获取当前平台
                        platform = self._get_platform(event)

                        # 保存搜索结果，使用用户消息ID作为键
                        results = data.get("results")
                        if results is None:
                            results = []
                        self.search_results[user_message_id] = {
                            "songs": results,
                            "platform": platform  # 保存平台信息
                        }
                        logger.info(f"搜索结果已保存，用户消息ID: {user_message_id}, 歌曲数: {len(results)}")

                        # 使用 drawer 绘制图片
                        image_bytes = await self.drawer.draw_search_result(keyword, result_data, session)

                        if image_bytes:
                            # 构建提示文本（在文本中嵌入用户消息ID，用于后续匹配）
                            hint_text = f"🎵 搜索结果: {keyword}\n共找到 {result_data.get('total', 0)} 首歌曲\n💡 点击回复按钮并输入序号即可播放，例如: 1\n[MID:{user_message_id}]"

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

            # 检查 songs 是否为 None
            if songs is None:
                logger.error("API 返回的 results 为 None")
                result["songs"] = [{"cover_url": None, "text": "搜索结果为空"}]
                return result

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
                    cover_url = f"{self.api_base_url}/api/music/cover/{song_id}"

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
        logger.info(f"_get_platform 开始执行，event 类型: {type(event)}")

        # 尝试从事件中获取平台信息
        logger.info(f"检查 event.platform: {hasattr(event, 'platform')}")
        if hasattr(event, 'platform'):
            platform = event.platform
            logger.info(f"event.platform 类型: {type(platform)}, 值: {platform}")
            # 处理 PlatformMetadata 对象
            if hasattr(platform, 'name'):
                result = platform.name.lower()
                logger.info(f"从 platform.name 获取到: {result}")
                return result
            elif isinstance(platform, str):
                result = platform.lower()
                logger.info(f"从 platform 字符串获取到: {result}")
                return result

        # 尝试从 message_obj 中获取
        logger.info(f"检查 event.message_obj: {hasattr(event, 'message_obj')}")
        if hasattr(event, 'message_obj'):
            logger.info(f"检查 event.message_obj.platform: {hasattr(event.message_obj, 'platform')}")
            if hasattr(event.message_obj, 'platform'):
                platform = event.message_obj.platform
                logger.info(f"message_obj.platform 类型: {type(platform)}, 值: {platform}")
                # 处理 PlatformMetadata 对象
                if hasattr(platform, 'name'):
                    result = platform.name.lower()
                    logger.info(f"从 message_obj.platform.name 获取到: {result}")
                    return result
                elif isinstance(platform, str):
                    result = platform.lower()
                    logger.info(f"从 message_obj.platform 字符串获取到: {result}")
                    return result

        # 默认返回 qq
        logger.info("使用默认平台: qq")
        return 'qq'

    def _get_message_id(self, event: AstrMessageEvent) -> str:
        """获取消息ID"""
        # 尝试从 message_obj 中获取 message_id
        if hasattr(event, 'message_obj') and hasattr(event.message_obj, 'message_id'):
            message_id = event.message_obj.message_id
            logger.info(f"从 message_obj.message_id 获取到消息ID: {message_id}")
            return str(message_id)

        # 尝试从 message 对象中获取
        if hasattr(event, 'message_obj') and hasattr(event.message_obj, 'message'):
            components = event.message_obj.message
            # 查找是否有包含 message_id 的组件
            for comp in components:
                if hasattr(comp, 'message_id'):
                    logger.info(f"从组件中获取到消息ID: {comp.message_id}")
                    return str(comp.message_id)

        # 如果都获取不到，返回 session_id 作为备用
        logger.warning(f"无法获取消息ID，使用 session_id 作为备用: {event.session_id}")
        return str(event.session_id)

    @filter.regex(r"^/?\s*\d+$")
    async def play_music(self, event: AstrMessageEvent):
        """播放音乐（通过序号）"""
        logger.info(f"===== play_music 被触发 =====")
        logger.info(f"原始 message_str: {repr(event.message_str)}")
        logger.info(f"event 类型: {type(event)}")
        logger.info(f"event.message_str 类型: {type(event.message_str)}")

        msg_text = event.message_str.strip()
        logger.info(f"去除空白后的 message_str: {repr(msg_text)}")

        # 去除可能的前导斜杠
        msg_text = msg_text.lstrip('/')
        logger.info(f"去除斜杠后的 message_str: {repr(msg_text)}")

        # 去除所有空白字符
        msg_text = msg_text.strip()
        logger.info(f"去除所有空白后的 message_str: {repr(msg_text)}")

        # 检查是否是纯数字
        if not msg_text.isdigit():
            logger.info(f"消息不是纯数字: {repr(msg_text)}，跳过")
            return

        try:
            logger.info("开始调用 _get_platform")
            platform = self._get_platform(event)
            logger.info(f"当前平台: {platform}")
        except Exception as e:
            logger.error(f"_get_platform 调用失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            platform = 'telegram'  # Telegram 平台默认值

        # Discord 平台特殊处理：尝试从事件对象中获取引用消息
        reply_msg = None
        reply_message_id = None

        if platform == 'discord':
            logger.info("Discord 平台：尝试从事件对象获取引用消息")
            # Discord 平台可能在 event 对象中存储引用消息信息
            # 尝试多种可能的属性
            if hasattr(event, 'message_obj'):
                message_obj = event.message_obj

                # 方法1: 检查 message_obj 是否有 message_reference 属性
                if hasattr(message_obj, 'message_reference'):
                    logger.info(f"找到 message_reference: {message_obj.message_reference}")
                    msg_ref = message_obj.message_reference
                    if hasattr(msg_ref, 'message_id'):
                        reply_message_id = str(msg_ref.message_id)
                        logger.info(f"从 message_reference.message_id 获取到: {reply_message_id}")

                # 方法2: 检查 message_obj 是否有 raw_message 属性（原始 Discord 消息对象）
                if not reply_message_id and hasattr(message_obj, 'raw_message'):
                    raw_msg = message_obj.raw_message
                    logger.info(f"找到 raw_message: {type(raw_msg)}")
                    if hasattr(raw_msg, 'reference') and raw_msg.reference:
                        if hasattr(raw_msg.reference, 'message_id'):
                            reply_message_id = str(raw_msg.reference.message_id)
                            logger.info(f"从 raw_message.reference.message_id 获取到: {reply_message_id}")

                # 方法3: 检查 message_obj 是否有 referenced_message_id 属性
                if not reply_message_id and hasattr(message_obj, 'referenced_message_id'):
                    reply_message_id = str(message_obj.referenced_message_id)
                    logger.info(f"从 referenced_message_id 获取到: {reply_message_id}")

                # 方法4: 检查 message_obj.message 中的 Reply 组件（有些 Discord 适配器可能使用）
                if not reply_message_id and hasattr(message_obj, 'message'):
                    components = message_obj.message
                    if components:
                        for comp in components:
                            if hasattr(comp, 'type') and comp.type == 'Reply':
                                reply_msg = comp
                                logger.info(f"从消息链中找到 Reply 组件: {reply_msg}")
                                break

        # 非 Discord 平台：从消息链中查找 Reply 组件
        else:
            logger.info(f"检查 event 是否有 message_obj: {hasattr(event, 'message_obj')}")
            if hasattr(event, 'message_obj'):
                logger.info(f"检查 message_obj 是否有 message: {hasattr(event.message_obj, 'message')}")
                if hasattr(event.message_obj, 'message'):
                    components = event.message_obj.message
                    logger.info(f"消息链组件数量: {len(components) if components else 0}")
                    logger.info(f"消息链组件类型: {[type(c).__name__ for c in components] if components else []}")

                    # 遍历消息链查找 Reply 组件
                    for idx, comp in enumerate(components):
                        logger.info(f"组件 {idx}: type={type(comp).__name__}, hasattr type={hasattr(comp, 'type')}")
                        if hasattr(comp, 'type'):
                            logger.info(f"组件 {idx} type={comp.type}")
                            if comp.type == 'Reply':
                                reply_msg = comp
                                logger.info(f"找到 Reply 组件: {reply_msg}")
                                break

        # 如果没有找到引用消息，跳过播放
        if not reply_msg and not reply_message_id:
            logger.info("没有引用消息，跳过播放")
            return

        # 检查引用的消息发送者是否是机器人自己
        # Telegram 平台: sender_id 是数字, bot_id 可能是字符串名称
        # QQ 平台: 两者都是数字字符串
        # Discord 平台: 直接使用 reply_message_id，不需要验证发送者（因为 reply_message_id 是机器人发送的消息ID）

        if platform != 'discord' and reply_msg:
            # 非 Discord 平台需要验证发送者
            if hasattr(reply_msg, 'sender_id'):
                reply_sender_id = reply_msg.sender_id
                bot_id = event.get_self_id()

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

        # Discord 平台：尝试从引用消息的内容中获取用户消息 ID
        # 非 Discord 平台：从引用消息中获取被引用消息的消息ID
        if platform == 'discord':
            # Discord 平台：reply_message_id 是引用消息 ID（机器人发送的搜索结果消息）
            # 我们需要从引用消息的文本中提取用户消息 ID
            logger.info(f"Discord 平台：尝试从引用消息获取用户消息 ID")

            # 尝试从 message_obj 中获取引用消息的内容
            user_message_id = None
            if hasattr(event, 'message_obj') and hasattr(event.message_obj, 'message_obj'):
                # Discord 平台可能有 referenced_message 属性
                if hasattr(event.message_obj.message_obj, 'referenced_message'):
                    ref_msg = event.message_obj.message_obj.referenced_message
                    if hasattr(ref_msg, 'content'):
                        import re
                        mid_match = re.search(r'\[MID:(\d+)\]', ref_msg.content)
                        if mid_match:
                            user_message_id = mid_match.group(1)
                            logger.info(f"从引用消息内容中提取到用户消息ID: {user_message_id}")

            if not user_message_id:
                # 尝试其他方式获取引用消息内容
                if hasattr(event, 'message_obj') and hasattr(event.message_obj, 'raw_message'):
                    raw_msg = event.message_obj.raw_message
                    if hasattr(raw_msg, 'reference') and raw_msg.reference:
                        if hasattr(raw_msg.reference, 'resolved') and raw_msg.reference.resolved:
                            ref_msg = raw_msg.reference.resolved
                            if hasattr(ref_msg, 'content'):
                                import re
                                mid_match = re.search(r'\[MID:(\d+)\]', ref_msg.content)
                                if mid_match:
                                    user_message_id = mid_match.group(1)
                                    logger.info(f"从 raw_message.reference.resolved.content 中提取到用户消息ID: {user_message_id}")

            if not user_message_id:
                logger.error(f"无法从引用消息中提取用户消息 ID")
                return

            logger.info(f"Discord 平台：使用用户消息 ID = {user_message_id}")
            reply_message_id = user_message_id
        else:
            # 从引用消息中获取被引用消息的消息ID
            reply_message_id = None

            # 方法1: 从引用消息的文本中提取 [MID:xxx] 格式的消息ID
            if hasattr(reply_msg, 'text'):
                import re
                mid_match = re.search(r'\[MID:(\d+)\]', reply_msg.text)
                if mid_match:
                    reply_message_id = mid_match.group(1)
                    logger.info(f"从引用消息文本中提取到消息ID: {reply_message_id}")

            # 方法2: 如果没有找到，尝试直接使用Reply组件的id（这个是机器人回复的消息ID）
            if not reply_message_id and hasattr(reply_msg, 'id'):
                reply_message_id = str(reply_msg.id)
                logger.info(f"从 Reply 组件 id 获取到消息ID: {reply_message_id}")

            # 方法3: 尝试从message_id获取
            if not reply_message_id and hasattr(reply_msg, 'message_id'):
                reply_message_id = str(reply_msg.message_id)
                logger.info(f"从 Reply 组件 message_id 获取到消息ID: {reply_message_id}")

            if not reply_message_id:
                logger.error("无法从 Reply 组件获取消息ID")
                return

        logger.info(f"已保存的搜索结果消息ID: {list(self.search_results.keys())}")

        # 检查是否有匹配的搜索结果
        if reply_message_id not in self.search_results:
            logger.info(f"消息ID {reply_message_id} 没有对应的搜索结果，跳过播放")
            return

        search_data = self.search_results[reply_message_id]
        songs = search_data["songs"]
        logger.info(f"找到 {len(songs)} 首歌曲")

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
        audio_url = f"{self.api_base_url}/api/music/file/{song_id}"

        # 先返回播放链接
        send_type = "文件" if platform == 'discord' else "语音"
        yield event.chain_result([
            Comp.Plain(f"🎶 Neko云音乐。听见好音乐\n🔗 {play_url}\n🎵 正在发送音乐{send_type}，请稍后\n平台内均为无损音质，发送可能较慢，请耐心等待..."),
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
                        # Discord: 文件最大 10MB
                        # Telegram: 语音文件最大 50MB
                        # QQ: 语音消息通常限制在 10MB 以内
                        if platform == 'discord':
                            max_size_mb = 10
                        elif platform == 'telegram':
                            max_size_mb = 50
                        else:
                            max_size_mb = 10

                        # 根据平台选择音频格式
                        # Discord: MP3 格式
                        # Telegram: MP3 格式
                        # QQ: MP3 格式
                        audio_format = '.mp3'

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
                            yield event.plain_result(f"文件较大 ({temp_file_size_mb:.2f}MB)，正在压缩中，请稍候...")
                            
                            # 使用 ffmpeg 压缩音频
                            compressed_path = temp_path.replace(audio_format, f'_compressed{audio_format}')
                            try:
                                # 检查 ffmpeg 是否可用
                                import shutil
                                if not shutil.which('ffmpeg'):
                                    logger.error("ffmpeg 未安装，无法压缩音频")
                                    yield event.plain_result(f"音频文件过大 ({temp_file_size_mb:.2f}MB)，但 ffmpeg 未安装无法压缩\n请直接点击播放链接收听: {play_url}")
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
                                
                                # Ensure asyncio is available for subprocess creation
                                import asyncio
                                
                                process = await asyncio.create_subprocess_exec(
                                    *compress_cmd,
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE
                                )
                                
                                stdout, stderr = await process.communicate()
                                
                                if process.returncode != 0:
                                    logger.error(f"ffmpeg 压缩失败: {stderr.decode()}")
                                    yield event.plain_result(f"音频压缩失败，请直接点击播放链接收听: {play_url}")
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

                        # 发送音频
                        # Discord 平台使用 File 组件发送音频文件
                        # 其他平台使用 Record 组件发送语音
                        logger.info(f"开始发送音频到 {platform} 平台")

                        # 构建文件名（歌曲名 - 歌手.扩展名）
                        # 需要从歌曲信息中获取歌手名
                        artist = song.get("artist", song.get("singer", "未知歌手"))
                        # 清理文件名中的非法字符
                        import re
                        safe_song_name = re.sub(r'[<>:"/\\|?*]', '', song_name)
                        safe_artist = re.sub(r'[<>:"/\\|?*]', '', artist)
                        filename = f"{safe_song_name} - {safe_artist}{audio_format}"

                        # 重命名临时文件为歌曲名
                        new_temp_path = os.path.join(os.path.dirname(temp_path), filename)
                        try:
                            os.rename(temp_path, new_temp_path)
                            logger.info(f"文件已重命名: {temp_path} -> {new_temp_path}")
                            temp_path = new_temp_path
                        except Exception as rename_error:
                            logger.warning(f"重命名文件失败: {str(rename_error)}，使用原文件名")

                        try:
                            if platform == 'discord':
                                # Discord 使用 File 组件发送音频文件
                                # 传入文件名和文件路径
                                yield event.chain_result([
                                    Comp.File(name=filename, file=temp_path)
                                ])
                                logger.info("Discord 音频文件发送成功")
                            else:
                                # 其他平台使用 Record 组件发送语音
                                yield event.chain_result([
                                    Comp.Record(file=temp_path)
                                ])
                                logger.info("语音发送成功")
                        except Exception as send_error:
                            logger.error(f"发送失败: {str(send_error)}")
                            # 如果发送失败，提供备用方案
                            yield event.plain_result(f"⚠️ 发送失败，请直接点击播放链接收听: {play_url}")

                        # 清理临时文件：延迟到发送完成后再删（避免 Comp.Record 读取失败）
                        import asyncio
                        async def safe_cleanup(path):
                            try:
                                # 等待 1 秒，确保 AstrBot 已读取文件
                                await asyncio.sleep(1.0)
                                os.unlink(path)
                                logger.info(f"✅ 已清理临时文件: {path}")
                            except Exception as e:
                                logger.warning(f"⚠️ 清理临时文件失败（可忽略）: {e}")
                        # 在后台执行，不阻塞发送
                        asyncio.create_task(safe_cleanup(temp_path))
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