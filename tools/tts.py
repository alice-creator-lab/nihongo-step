#!/usr/bin/env python3
"""統一 TTS 入口：edge-tts 或 Azure Speech（24kHz 單聲道 48kbps MP3）。

TTS_ENGINE=azure 環境變數一開，全站生成工具就會改用 Azure；
預設仍是 edge，方便未設定金鑰時照舊運作。

Azure 的聲音名稱與 edge 不同：edge 只有 Nanami／Keita，Azure 另有
Mayu（女）、Daichi／Naoki（男）。這裡做一個對照，令舊腳本寫的
"ja-JP-NanamiNeural" 在 Azure 下自動變 Mayu。
"""
import os
import subprocess

EDGE_FROM_AZURE = {
    "ja-JP-MayuNeural": "ja-JP-NanamiNeural",
    "ja-JP-NaokiNeural": "ja-JP-KeitaNeural",
    "ja-JP-DaichiNeural": "ja-JP-KeitaNeural",
    "ja-JP-AoiNeural": "ja-JP-NanamiNeural",
}


def engine():
    return os.environ.get("TTS_ENGINE", "edge").strip().lower()


def azure_synth(text, out, voice="ja-JP-MayuNeural", rate=None):
    key = os.environ.get("AZURE_SPEECH_KEY", "")
    region = os.environ.get("AZURE_SPEECH_REGION", "")
    if not key or not region:
        raise RuntimeError("缺 AZURE_SPEECH_KEY／AZURE_SPEECH_REGION")
    import time
    import urllib.error
    import urllib.request
    lang = "ja-JP"
    p = f'<prosody rate="{rate}">' if rate else ""
    q = "</prosody>" if rate else ""
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">'
            f'<voice name="{voice}">{p}{text}{q}</voice></speak>').encode("utf-8")
    req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml,
        headers={"Ocp-Apim-Subscription-Key": key,
                 "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                 "User-Agent": "nihongo-step"},
        method="POST")
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if len(data) > 500:
                open(out, "wb").write(data)
                return True
            last = "empty"
        except Exception as e:                     # 429／網絡錯誤：退避重試
            last = e
            time.sleep(1.5 * (attempt + 1))
    print("  azure fail", out, last, flush=True)
    return False


def say(text, out, voice="ja-JP-MayuNeural", rate=None, retries=3):
    """合成一段音檔，成功回 True。"""
    if engine() == "azure":
        return azure_synth(text, out, voice, rate)
    ev = EDGE_FROM_AZURE.get(voice, voice)
    for _ in range(retries):
        r = subprocess.run(["edge-tts", "--voice", ev, "--text", text, "--write-media", out],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 900:
            return True
    return False
