sudo apt update && sudo apt upgrade -y

//필요 패키지 다운
wget https://github.com/doceme/py-spidev/archive/refs/heads/master.zip
unzip master.zip
cd py-spidev-master
python3 setup.py install

//설치 확인
python3 -c "import spidev; print(spidev)" 
//
