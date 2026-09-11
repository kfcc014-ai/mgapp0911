MG 금융 데이터 CRUD 대시보드 - Streamlit 실행 방법

1. app.py와 requirements.txt를 같은 폴더에 둡니다.
2. 터미널에서 해당 폴더로 이동합니다.
3. 패키지를 설치합니다.

   python -m pip install -r requirements.txt

4. 앱을 실행합니다.

   streamlit run app.py

5. 브라우저에서 앱이 열리면 Supabase URL과 Publishable/anon Key를 입력하고 연결합니다.

주의
- Service Role / Secret Key는 입력하지 마세요.
- 공개 배포 환경에서는 Supabase 인증과 RLS 정책을 적용하세요.
