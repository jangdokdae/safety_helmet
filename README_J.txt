<<<항상 코드 git push 전에 git pull 먼저 하기>>



//라파에서 ssh 키 생성 뭐 뜨면 다 엔터 누르기
//비공개키와 공개키가 생성됨
ssh-keygen -t rsa -b 4096 -C "your_email@gmail.com"

//ssh키 확인
cat ~/.ssh/id_rsa.pub


GitHub에 SSH 키 등록하기
GitHub에 로그인
오른쪽 위 프로필 아이콘 클릭 → Settings 선택
왼쪽 메뉴에서 SSH and GPG keys 클릭
New SSH key 버튼 클릭
Title: Raspberry Pi (아무 이름 가능)
Key: 아까 복사한 SSH 공개 키를 붙여넣기 (Ctrl + V)
Add SSH key 클릭
//확인
ssh -T git@github.com

//내 git 복사
git clone git@github.com:jangdokdae/safety_helmet.git

//git 사용하려면 네 정보 입력
git config --global user.email "your-email@example.com"
git config --global user.name "Your Name"

//
sudo apt update && sudo apt upgrade -y

//필요 패키지 다운
wget https://github.com/doceme/py-spidev/archive/refs/heads/master.zip
unzip master.zip
cd py-spidev-master
python3 setup.py install

//설치 확인 /
python3 -c "import spidev; print(spidev)" 

//github에 새 파일 추가 & 업데이트
cd ~/safety_helmet
git add .
git status  # (추가된 파일 확인)
git commit -m "새 파일 추가 및 프로젝트 업데이트"
git push origin main

