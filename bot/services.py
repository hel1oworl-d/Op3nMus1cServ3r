import os
import uuid
from pathlib import Path
from mutagen import File as MutagenFile
from aiogram import Bot
from aiogram.types import Audio, Document

TRACKS_DIR = Path("/root/Hel1oMus1cServer/uploads/tracks")
TRACKS_DIR.mkdir(parents=True, exist_ok=True)

async def download_media_file(bot: Bot, media: Audio | Document) -> tuple[str, Path]:
    orig_name = getattr(media, "file_name", None) or "track.mp3"
    ext = Path(orig_name).suffix or ".mp3"
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    dest_path = TRACKS_DIR / unique_filename
    await bot.download(media, destination=dest_path)
    return orig_name, dest_path

def parse_audio_metadata(file_path: Path, media: Audio | Document) -> tuple[str | None, str | None]:
    title = getattr(media, "title", None)
    artist = getattr(media, "performer", None)
    if title and artist:
        return title.strip(), artist.strip()
    try:
        audio = MutagenFile(str(file_path), easy=True)
        if audio:
            if not title and "title" in audio:
                title = audio["title"][0]
            if not artist and "artist" in audio:
                artist = audio["artist"][0]
    except Exception:
        pass
    return title, artist

def remove_temp_file(file_path: str | None) -> None:
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
