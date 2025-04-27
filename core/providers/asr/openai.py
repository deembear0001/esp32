import time
import io
import wave
import os
from typing import Optional, Tuple, List
import json  # 添加json模块导入

import opuslib_next
from core.providers.asr.base import ASRProviderBase

from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        self.model = config.get("model", "whisper-large-v3")
        self.api_url = config.get("api_url", "https://api.groq.com/openai/v1/audio/transcriptions")
        self.api_key = config.get("api_key")
        self.seg_duration = 15000

    def save_audio_to_file(self, opus_data: List[bytes], session_id: str) -> str:
        pass

    async def _send_request(self, audio_data: List[bytes], segment_size: int) -> Optional[str]:
        """使用 Groq API 进行语音识别"""
        try:
            import aiohttp
            from aiohttp import FormData
            
            # 正确引用参数名 audio_data
            valid_audio = []
            for chunk in audio_data:  # 此处变量名已修正
                if isinstance(chunk, bytes):
                    valid_audio.append(chunk)
                else:
                    logger.bind(tag=TAG).warning(f"非法音频数据类型: {type(chunk)}")
            
            full_audio = b''.join(valid_audio)
            
            # 构建 multipart/form-data
            headers = {"Authorization": f"Bearer {self.api_key}"}
            data = FormData()
            data.add_field('model', self.model)
            data.add_field('file', 
                          io.BytesIO(full_audio),
                          filename='audio.wav',
                          content_type='audio/wav')
            data.add_field('response_format', 'text')

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    data=data
                ) as response:
                    if response.status == 200:
                        text = await response.text()
                        # 尝试解析JSON并提取文本
                        try:
                            if text and text.strip().startswith('{') and text.strip().endswith('}'):
                                json_data = json.loads(text)
                                # 检查并提取 text 字段
                                if 'data' in json_data and 'text' in json_data['data']:
                                    return json_data['data']['text'].strip()
                                elif 'text' in json_data:
                                    return json_data['text'].strip()
                        except json.JSONDecodeError:
                            logger.bind(tag=TAG).error(f"JSON 解析错误: {text}")
                        return text.strip()
                    else:
                        error_detail = await response.text()
                        logger.bind(tag=TAG).error(
                            f"Groq API 请求失败: 状态码 {response.status}, 错误信息: {error_detail}"
                        )
                        return None
        except Exception as e:
            logger.bind(tag=TAG).error(f"Groq API 请求异常: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def decode_opus(opus_data: List[bytes], session_id: str) -> List[bytes]:
        decoder = opuslib_next.Decoder(16000, 1)  # 16kHz, 单声道
        pcm_data = []
        for opus_packet in opus_data:
            try:
                pcm_frame = decoder.decode(opus_packet, 960)  # 960 samples = 60ms
                pcm_data.append(pcm_frame)
            except opuslib_next.OpusError as e:
                logger.bind(tag=TAG).error(f"Opus解码错误: {e}", exc_info=True)
        return pcm_data

    @staticmethod
    def read_wav_info(data: io.BytesIO = None) -> (int, int, int, int, int):
        with io.BytesIO(data) as _f:
            wave_fp = wave.open(_f, 'rb')
            nchannels, sampwidth, framerate, nframes = wave_fp.getparams()[:4]
            wave_bytes = wave_fp.readframes(nframes)
        return nchannels, sampwidth, framerate, nframes, len(wave_bytes)

    async def speech_to_text(self, opus_data: List[bytes], session_id: str) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本"""
        try:
            # 合并所有opus数据包
            pcm_data = self.decode_opus(opus_data, session_id)
            combined_pcm_data = b''.join(pcm_data)

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)  # 设置声道数
                wav_file.setsampwidth(2)  # 设置采样宽度
                wav_file.setframerate(16000)  # 设置采样率
                wav_file.writeframes(combined_pcm_data)  # 写入 PCM 数据

            # 获取封装后的 WAV 数据
            wav_data = wav_buffer.getvalue()
            nchannels, sampwidth, framerate, nframes, wav_len = self.read_wav_info(wav_data)
            size_per_sec = nchannels * sampwidth * framerate
            segment_size = int(size_per_sec * self.seg_duration / 1000)

            # 语音识别
            start_time = time.time()

            # 关键修复点：将单个bytes包装为列表
            text = await self._send_request([wav_data], segment_size)  # 注意列表包装
            
            if text:
                logger.bind(tag=TAG).debug(f"语音识别耗时: {time.time() - start_time:.3f}s | 结果: {text}")
                return text, None
            return "", None
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}", exc_info=True)
            return "", None