"""
Storage Service - File storage and management operations.

This module provides utilities for managing Excel file storage,
including copying, moving, and cleanup operations.
"""

import os
import shutil
import hashlib
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Default storage directory
DEFAULT_MODELS_DIR = 'models/'


class StorageService:
    """
    Framework-agnostic storage service for file management.
    
    Handles Excel file storage, hashing, and cleanup operations.
    """
    
    def __init__(self, models_dir: str = DEFAULT_MODELS_DIR):
        """
        Initialize storage service.
        
        Args:
            models_dir: Directory to store Excel files (default: 'models/')
        """
        self.models_dir = models_dir
        self._ensure_directory_exists()
    
    def _ensure_directory_exists(self):
        """Ensure the models directory exists."""
        Path(self.models_dir).mkdir(parents=True, exist_ok=True)
        logger.debug(f"Storage directory ensured: {self.models_dir}")
    
    def compute_file_hash(self, file_path: str, algorithm: str = 'sha256') -> str:
        """
        Compute hash of a file.
        
        Args:
            file_path: Path to file
            algorithm: Hash algorithm ('sha256', 'md5', 'sha1')
        
        Returns:
            Hex digest of file hash
        """
        if algorithm == 'sha256':
            hasher = hashlib.sha256()
        elif algorithm == 'md5':
            hasher = hashlib.md5()
        elif algorithm == 'sha1':
            hasher = hashlib.sha1()
        else:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")
        
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                hasher.update(byte_block)
        
        file_hash = hasher.hexdigest()
        logger.debug(f"Computed {algorithm} hash for {file_path}: {file_hash[:16]}...")
        return file_hash
    
    def store_file(self, source_path: str, file_hash: str, 
                   use_hash_name: bool = True) -> str:
        """
        Store file in models directory.
        
        Args:
            source_path: Path to source file
            file_hash: Hash of the file (for naming)
            use_hash_name: If True, use hash as filename; if False, use original name
        
        Returns:
            Path to stored file
        """
        self._ensure_directory_exists()
        
        ext = Path(source_path).suffix
        
        if use_hash_name:
            # Use first 16 chars of hash as filename
            dest_filename = f"{file_hash[:16]}{ext}"
        else:
            # Use original filename
            dest_filename = Path(source_path).name
        
        dest_path = Path(self.models_dir) / dest_filename
        
        # Copy file
        shutil.copy2(source_path, dest_path)
        logger.info(f"Stored file: {source_path} -> {dest_path}")
        
        return str(dest_path)
    
    def move_file(self, source_path: str, file_hash: str,
                  use_hash_name: bool = True) -> str:
        """
        Move file to models directory (removes source).
        
        Args:
            source_path: Path to source file
            file_hash: Hash of the file (for naming)
            use_hash_name: If True, use hash as filename; if False, use original name
        
        Returns:
            Path to stored file
        """
        self._ensure_directory_exists()
        
        ext = Path(source_path).suffix
        
        if use_hash_name:
            dest_filename = f"{file_hash[:16]}{ext}"
        else:
            dest_filename = Path(source_path).name
        
        dest_path = Path(self.models_dir) / dest_filename
        
        # Move file
        shutil.move(source_path, dest_path)
        logger.info(f"Moved file: {source_path} -> {dest_path}")
        
        return str(dest_path)
    
    def file_exists(self, file_hash: str, extension: str = '.xlsx') -> Optional[str]:
        """
        Check if a file with given hash exists in storage.
        
        Args:
            file_hash: File hash to check
            extension: File extension (default: .xlsx)
        
        Returns:
            Path to file if exists, None otherwise
        """
        filename = f"{file_hash[:16]}{extension}"
        file_path = Path(self.models_dir) / filename
        
        if file_path.exists():
            return str(file_path)
        return None
    
    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from storage.
        
        Args:
            file_path: Path to file to delete
        
        Returns:
            True if file was deleted, False if file didn't exist
        """
        path = Path(file_path)
        
        if path.exists():
            path.unlink()
            logger.info(f"Deleted file: {file_path}")
            return True
        else:
            logger.warning(f"File not found for deletion: {file_path}")
            return False
    
    def get_file_info(self, file_path: str) -> Optional[dict]:
        """
        Get information about a stored file.
        
        Args:
            file_path: Path to file
        
        Returns:
            Dictionary with file info, or None if file doesn't exist
        """
        path = Path(file_path)
        
        if not path.exists():
            return None
        
        stat = path.stat()
        
        return {
            'path': str(path),
            'name': path.name,
            'size_bytes': stat.st_size,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'created': datetime.fromtimestamp(stat.st_ctime),
            'modified': datetime.fromtimestamp(stat.st_mtime),
            'extension': path.suffix
        }
    
    def list_files(self, extension: Optional[str] = None) -> list:
        """
        List all files in storage directory.
        
        Args:
            extension: Filter by extension (e.g., '.xlsx'), None for all files
        
        Returns:
            List of file paths
        """
        self._ensure_directory_exists()
        
        models_path = Path(self.models_dir)
        
        if extension:
            files = list(models_path.glob(f"*{extension}"))
        else:
            files = list(models_path.glob("*"))
        
        # Filter out directories
        files = [f for f in files if f.is_file()]
        
        return [str(f) for f in files]
    
    def get_storage_stats(self) -> dict:
        """
        Get statistics about storage directory.
        
        Returns:
            Dictionary with storage statistics
        """
        self._ensure_directory_exists()
        
        models_path = Path(self.models_dir)
        files = [f for f in models_path.glob("*") if f.is_file()]
        
        total_size = sum(f.stat().st_size for f in files)
        
        # Count by extension
        extensions = {}
        for f in files:
            ext = f.suffix or 'no_extension'
            extensions[ext] = extensions.get(ext, 0) + 1
        
        return {
            'total_files': len(files),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'total_size_gb': round(total_size / (1024 * 1024 * 1024), 2),
            'files_by_extension': extensions,
            'storage_directory': str(models_path.absolute())
        }
    
    def cleanup_temp_files(self, temp_dir: str, older_than_hours: int = 24) -> int:
        """
        Clean up temporary files older than specified hours.
        
        Args:
            temp_dir: Temporary directory to clean
            older_than_hours: Remove files older than this many hours
        
        Returns:
            Number of files deleted
        """
        temp_path = Path(temp_dir)
        
        if not temp_path.exists():
            return 0
        
        current_time = datetime.now().timestamp()
        cutoff_time = current_time - (older_than_hours * 3600)
        
        deleted_count = 0
        
        for file_path in temp_path.glob("*"):
            if file_path.is_file():
                file_mtime = file_path.stat().st_mtime
                if file_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        logger.debug(f"Cleaned up temp file: {file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting temp file {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} temporary files")
        
        return deleted_count
    
    def validate_file_extension(self, file_path: str, 
                               allowed_extensions: list = None) -> bool:
        """
        Validate file extension.
        
        Args:
            file_path: Path to file
            allowed_extensions: List of allowed extensions (e.g., ['.xlsx', '.xlsm'])
        
        Returns:
            True if extension is allowed, False otherwise
        """
        if allowed_extensions is None:
            allowed_extensions = ['.xlsx', '.xlsm']
        
        ext = Path(file_path).suffix.lower()
        is_valid = ext in [e.lower() for e in allowed_extensions]
        
        if not is_valid:
            logger.warning(f"Invalid file extension: {ext} (allowed: {allowed_extensions})")
        
        return is_valid
    
    def get_file_size_mb(self, file_path: str) -> float:
        """
        Get file size in megabytes.
        
        Args:
            file_path: Path to file
        
        Returns:
            File size in MB
        """
        path = Path(file_path)
        
        if not path.exists():
            return 0.0
        
        size_bytes = path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        
        return round(size_mb, 2)
    
    def validate_file_size(self, file_path: str, max_size_mb: int = 100) -> bool:
        """
        Validate that file size is within limit.
        
        Args:
            file_path: Path to file
            max_size_mb: Maximum allowed size in MB
        
        Returns:
            True if size is within limit, False otherwise
        """
        size_mb = self.get_file_size_mb(file_path)
        is_valid = size_mb <= max_size_mb
        
        if not is_valid:
            logger.warning(f"File size {size_mb} MB exceeds limit of {max_size_mb} MB")
        
        return is_valid