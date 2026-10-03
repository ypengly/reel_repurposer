@echo off
python -m pip install -r requirements.txt || exit /b 1
pyinstaller --noconfirm --windowed --name ReelRepurposer main.py || exit /b 1
echo Done: dist\ReelRepurposer\ReelRepurposer.exe  (FFmpeg must be installed on the target PC's PATH)
