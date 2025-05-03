import os
import shutil
from pathlib import Path

def setup_avatars():
    # Define paths
    static_dir = Path(__file__).parent / 'static'
    avatars_dir = static_dir / 'avatars'
    
    # Create directories if they don't exist
    avatars_dir.mkdir(parents=True, exist_ok=True)
    
    # Default avatars
    avatars = {
        'female1.jpg': 'https://i.imgur.com/1234567.jpg',  # Replace with actual URLs
        'female2.jpg': 'https://i.imgur.com/2345678.jpg',
        'female3.jpg': 'https://i.imgur.com/3456789.jpg',
        'female4.jpg': 'https://i.imgur.com/4567890.jpg',
        'male1.jpg': 'https://i.imgur.com/5678901.jpg',
        'male2.jpg': 'https://i.imgur.com/6789012.jpg',
        'male3.jpg': 'https://i.imgur.com/7890123.jpg',
        'male4.jpg': 'https://i.imgur.com/8901234.jpg',
    }
    
    # Copy avatar files
    for avatar in avatars:
        src = Path(__file__).parent / 'default_avatars' / avatar
        if src.exists():
            shutil.copy(src, avatars_dir / avatar)

if __name__ == "__main__":
    setup_avatars()
