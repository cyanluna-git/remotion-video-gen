\*\*화면 동작:\*\*

1\. OQC 로그인 페이지 → Microsoft SSO 버튼 클릭

2\. 대시보드 진입 → KPI 카드 (실행 현황, 완료율, 장비 상태) 잠깐 보여주기

3\. 좌측 메뉴를 가볍게 훑어보기 (전체 구조 파악용)



\*\*자막/캡션:\*\*

\- "Sign in with Microsoft SSO"

\- "Dashboard: real-time overview of all inspections"



\---



\#### Scene 2: 시나리오 디자인 (약 30\~40초)



\*\*화면 동작:\*\*

1\. 좌측 메뉴 → \*\*Scenario Designer\*\* 클릭

2\. 기존 시나리오 하나 열기 (예: EUV Gen2 FT\&CC 중 하나)

3\. 시나리오 구조 보여주기: Feature → Scenario → Step 계층

4\. Step 하나 클릭해서 상세 내용 보여주기 (Given/When/Then, Modbus 주소 등)

5\. SOP 이미지가 포함된 스텝 하나 보여주기 (시각 가이드)



\*\*자막/캡션:\*\*

\- "Design test scenarios using BDD (Gherkin) format"

\- "Each step maps to a specific equipment check"

\- "SOP images guide operators through each step"



\---



\#### Scene 3: 테스트 실행 (약 40\~50초) ⭐ 핵심 장면



\*\*화면 동작:\*\*

1\. \*\*Edge Tester UI\*\*로 전환 (별도 탭 또는 /edge/ 경로)

2\. \*\*New Inspection\*\* 시작 → 카탈로그 선택 화면

&#x20;  - 테스트 세트 목록 + 시나리오 수 + 예상 시간 보여주기

3\. 테스트 세트 1\~2개 선택 → \*\*Start Selected\*\* 클릭

4\. 실행 화면에서:

&#x20;  - 시나리오 목록 좌측에 진행 상태 보이기

&#x20;  - 하나의 시나리오 클릭 → 스텝별 체크리스트 보여주기

&#x20;  - Pass/Fail 판정하는 모습 (1\~2개 스텝)

&#x20;  - 사진 첨부하는 모습 (카메라 아이콘 클릭 → 업로드)

5\. Corrective Action 입력하는 모습 (Fail 케이스)



\*\*자막/캡션:\*\*

\- "Select test sets — see scenario count and estimated time"

\- "Execute step-by-step with pass/fail judgments"

\- "Attach photo evidence directly from the field"

\- "Record corrective actions for failed items"



\---



\#### Scene 4: 결과 동기화 \& 보고서 (약 30초)



\*\*화면 동작:\*\*

1\. 실행 완료 후 → 결과 요약 화면 (전체 Pass/Fail 통계)

2\. \*\*Server Dashboard\*\*로 돌아가기

3\. \*\*Execution Reports\*\* 메뉴 클릭

4\. 방금 완료한 실행 선택 → 보고서 미리보기

&#x20;  - 커버 페이지, 통계 요약, 시나리오별 결과, 증빙 사진

5\. \*\*Export DOCX\*\* 버튼 클릭 (원클릭 보고서 생성)



\*\*자막/캡션:\*\*

\- "Results sync automatically from Edge to Server"

\- "Generate compliance reports with one click"

\- "Full audit trail: every action timestamped"



\---



\#### Scene 5: 장비 모니터링 (약 15초, 엔딩)



\*\*화면 동작:\*\*

1\. \*\*System Connectivity\*\* 패널 열기 → 장비 연결 상태 확인

2\. 실시간 데이터가 들어오는 모습 잠깐 보여주기

3\. 화면 페이드아웃 → 엔딩 타이틀카드



\*\*자막/캡션:\*\*

\- "Real-time equipment monitoring via Modbus TCP"

\- "OQC Digitalization Platform — Edwards Vacuum"



\---



\### 녹화 팁



| 항목 | 권장사항 |

|------|---------|

| \*\*해상도\*\* | 1920×1080 (Full HD) |

| \*\*브라우저\*\* | Chrome, 탭 1개만, 북마크바 숨김 |

| \*\*마우스\*\* | 천천히, 의도적으로 움직이기. 클릭 전 0.5초 멈춤 |

| \*\*속도\*\* | 각 화면에서 2\~3초 머물기 (보는 사람이 읽을 시간) |

| \*\*데이터\*\* | 미리 테스트 데이터 준비 (빈 화면 방지) |

| \*\*녹화 도구\*\* | OBS 또는 Windows 게임바 (Win+G) |

| \*\*화면 전환\*\* | Scene 간 자연스럽게 (새 탭 전환 or 메뉴 네비게이션) |



\### Pipeline 실행 방법



녹화 완료 후:

```bash

cd /home/edwards/cyanluna.dev/remotion-video-gen



\# scenario.json은 위 시나리오 기반으로 생성

./pipeline.sh recording.mp4 scenarios/oqc-intro.json

```



→ 자동으로: 분석 → AI 편집 → 타이틀카드 삽입 → 자막 생성 → 최종 MP4 출력

