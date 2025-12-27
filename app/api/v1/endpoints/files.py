from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from app.api import deps
from app.core.config import settings
from app.models.user import User
import aiofiles
from pathlib import Path
import uuid
import os

router = APIRouter()

@router.post("/upload", response_model=dict)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Загрузка файла админом.
    Возвращает прямую ссылку на файл.
    """
    # Проверяем расширение файла (опционально, пока разрешаем все)
    # Определяем путь сохранения
    upload_dir = Path(settings.STORAGE_FILES_LOCAL_PATH)
    if not upload_dir.is_absolute():
        upload_dir = Path(settings.STORAGE_LOCAL_PATH).parent.parent / upload_dir
    
    # Создаем директорию если ее нет (должна быть создана в main.py, но на всякий случай)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем уникальное имя файла, чтобы избежать коллизий
    # Сохраняем оригинальное расширение
    file_ext = os.path.splitext(file.filename)[1]
    # Используем оригинальное имя, но добавляем UUID если такой файл существует
    # Или просто генерируем UUID для безопасности и уникальности.
    # Для ресурсов КС 1.6 часто важны имена файлов (например .bsp карты), поэтому лучше сохранить оригинальное имя.
    # Но если файл с таким именем есть, добавим суффикс.
    
    safe_filename = file.filename
    file_path = upload_dir / safe_filename
    
    if file_path.exists():
        # Если файл существует, добавляем короткий UUID к имени
        name_without_ext = os.path.splitext(file.filename)[0]
        unique_suffix = str(uuid.uuid4())[:8]
        safe_filename = f"{name_without_ext}_{unique_suffix}{file_ext}"
        file_path = upload_dir / safe_filename
        
    try:
        async with aiofiles.open(file_path, 'wb') as out_file:
            # Читаем чанками, чтобы не забивать память
            while content := await file.read(1024 * 1024):  # 1MB chunks
                await out_file.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save file: {str(e)}"
        )
    finally:
        await file.close()
        
    # Формируем URL
    # Используем BACKEND_BASE_URL (http://localhost:8000) + STORAGE_FILES_BASE_URL (/static/files) + filename
    # Важно: STORAGE_FILES_BASE_URL должен соответствовать тому, как смонтирована статика в main.py
    # В main.py: app.mount("/static", StaticFiles(directory=str(uploads_path.parent)), name="static")
    # uploads_path.parent - это папка "uploads".
    # STORAGE_FILES_LOCAL_PATH = "uploads/files"
    # Значит файлы лежат в uploads/files.
    # Если мы запрашиваем /static/files/filename, request будет искать в uploads/files/filename.
    # Это корректно.
    
    url = f"{settings.BACKEND_BASE_URL}{settings.STORAGE_FILES_BASE_URL}/{safe_filename}"
    
    return {
        "filename": safe_filename,
        "url": url
    }

@router.get("/", response_model=list[dict])
async def list_files(
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Список всех загруженных файлов.
    """
    upload_dir = Path(settings.STORAGE_FILES_LOCAL_PATH)
    if not upload_dir.is_absolute():
        upload_dir = Path(settings.STORAGE_LOCAL_PATH).parent.parent / upload_dir
    
    if not upload_dir.exists():
        return []
        
    files = []
    for entry in os.scandir(upload_dir):
        if entry.is_file():
            stat = entry.stat()
            url = f"{settings.BACKEND_BASE_URL}{settings.STORAGE_FILES_BASE_URL}/{entry.name}"
            files.append({
                "filename": entry.name,
                "url": url,
                "size": stat.st_size,
                "created_at": stat.st_ctime
            })
            
    # Сортируем по дате создания (новые сверху)
    files.sort(key=lambda x: x["created_at"], reverse=True)
    return files

@router.delete("/{filename}", response_model=dict)
async def delete_file(
    filename: str,
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Удаление файла.
    """
    upload_dir = Path(settings.STORAGE_FILES_LOCAL_PATH)
    if not upload_dir.is_absolute():
        upload_dir = Path(settings.STORAGE_LOCAL_PATH).parent.parent / upload_dir
        
    file_path = upload_dir / filename
    
    # Проверка на выход за пределы директории (path traversal)
    try:
        file_path = file_path.resolve()
        upload_dir = upload_dir.resolve()
        if not str(file_path).startswith(str(upload_dir)):
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid filename"
            )
    except Exception:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename"
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
        
    try:
        os.remove(file_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not delete file: {str(e)}"
        )
        
    return {"status": "success", "message": f"File {filename} deleted"}
