import streamlit as st
import pandas as pd
import folium
import requests
import re

from streamlit_folium import st_folium
from folium.plugins import MarkerCluster

# =========================================================
# 카카오 REST API 키 입력
# =========================================================

# 반드시 REST API 키 사용
# JavaScript 키 사용 금지

KAKAO_API_KEY = "e2476f6d5b4c7e1c3e550e59f6154114"

# =========================================================
# 기본 설정
# =========================================================

st.set_page_config(
    page_title="폐기물 접수 지도",
    layout="wide"
)

st.title("폐기물 접수 지도 시스템")

st.write("엑셀 파일 업로드 시 접수 위치를 지도에 표시합니다.")

# =========================================================
# 엑셀 업로드
# =========================================================

uploaded_file = st.file_uploader(
    "엑셀 파일 업로드",
    type=["xlsx", "xls"]
)

# =========================================================
# 주소 정리 함수
# =========================================================

def clean_address(addr):

    if pd.isna(addr):
        return ""

    addr = str(addr)

    # 줄바꿈 제거
    addr = addr.replace("\n", " ")

    # 공백 정리
    addr = " ".join(addr.split())

    # 동 + 숫자 띄어쓰기
    addr = re.sub(r"동(\d)", r"동 \1", addr)

    # 로 + 숫자 띄어쓰기
    addr = re.sub(r"로(\d)", r"로 \1", addr)

    # 길 + 숫자 띄어쓰기
    addr = re.sub(r"길(\d)", r"길 \1", addr)

    # 가길/나길/다길
    addr = re.sub(r"가길(\d)", r"가길 \1", addr)
    addr = re.sub(r"나길(\d)", r"나길 \1", addr)
    addr = re.sub(r"다길(\d)", r"다길 \1", addr)

    return addr

# =========================================================
# 카카오 주소 검색 함수
# =========================================================

@st.cache_data(show_spinner=False)
def get_coordinates(road_address, jibun_address):

    headers = {
        "Authorization": f"KakaoAK {KAKAO_API_KEY}"
    }

    road_address = clean_address(road_address)
    jibun_address = clean_address(jibun_address)

    search_list = [
        road_address,
        jibun_address
    ]

    for address in search_list:

        if not address:
            continue

        try:

            url = "https://dapi.kakao.com/v2/local/search/address.json"

            params = {
                "query": address
            }

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=5
            )

            result = response.json()

            # 검색 성공
            if "documents" in result:

                if len(result["documents"]) > 0:

                    x = result["documents"][0]["x"]
                    y = result["documents"][0]["y"]

                    return float(y), float(x), address

        except:
            pass

    return None, None, None

# =========================================================
# 파일 업로드 후 실행
# =========================================================

if uploaded_file:

    try:

        # =====================================================
        # 원본 엑셀 읽기
        # =====================================================

        raw_df = pd.read_excel(
            uploaded_file,
            header=None
        )

        # =====================================================
        # 헤더 행 자동 찾기
        # =====================================================

        header_row = None

        for idx, row in raw_df.iterrows():

            row_text = "".join(row.astype(str))

            if "연락처" in row_text and "품명" in row_text:

                header_row = idx
                break

        # 헤더 못 찾은 경우
        if header_row is None:

            st.error("엑셀 헤더를 찾을 수 없습니다.")

            st.stop()

        # =====================================================
        # 실제 데이터 다시 읽기
        # =====================================================

        df = pd.read_excel(
            uploaded_file,
            header=header_row
        )

        # =====================================================
        # 컬럼명 정리
        # =====================================================

        df.columns = (
            df.columns
            .astype(str)
            .str.strip()
            .str.replace("\n", "", regex=False)
            .str.replace(" ", "", regex=False)
        )

        # =====================================================
        # Unnamed 컬럼 제거
        # =====================================================

        df = df.loc[
            :,
            ~df.columns.str.contains("^Unnamed")
        ]

        # =====================================================
        # 컬럼 확인
        # =====================================================

        st.subheader("엑셀 컬럼 확인")

        st.write(df.columns.tolist())

        # =====================================================
        # 필수 컬럼 체크
        # =====================================================

        required_columns = [
            "연락처",
            "품명",
            "수량",
            "지번주소",
            "도로명주소"
        ]

        missing_columns = []

        for col in required_columns:

            if col not in df.columns:

                missing_columns.append(col)

        if missing_columns:

            st.error(f"필수 컬럼 누락: {missing_columns}")

            st.stop()

        # =====================================================
        # 데이터 표시
        # =====================================================

        st.subheader("업로드 데이터")

        st.dataframe(df)

        # =====================================================
        # 카카오 API 테스트
        # =====================================================

        test_lat, test_lon, test_addr = get_coordinates(
            "서울 마포구 망원로 3길 21",
            "서울 마포구 망원동 429-2"
        )

        if test_lat and test_lon:

            st.success("카카오 API 정상 연결")

        else:

            st.error("""
            카카오 API 연결 실패

            아래 사항 확인:

            1. REST API 키 사용 여부
            2. 카카오맵 활성화 여부
            """)

            st.stop()

        # =====================================================
        # 지도 생성
        # =====================================================

        m = folium.Map(
            location=[37.5665, 126.9780],
            zoom_start=12
        )

        marker_cluster = MarkerCluster().add_to(m)

        # =====================================================
        # 진행률
        # =====================================================

        progress_bar = st.progress(0)

        total_count = len(df)

        success_count = 0

        fail_count = 0

        fail_addresses = []

        # 지도 중심 계산용
        lat_list = []
        lon_list = []

        # =====================================================
        # 데이터 반복
        # =====================================================

        for idx, row in df.iterrows():

            try:

                # -------------------------------------------------
                # 데이터 읽기
                # -------------------------------------------------

                road_address = str(row["도로명주소"])

                jibun_address = str(row["지번주소"])

                item = str(row["품명"])

                qty = str(row["수량"])

                phone = str(row["연락처"])

                # -------------------------------------------------
                # 좌표 검색
                # -------------------------------------------------

                lat, lon, final_address = get_coordinates(
                    road_address,
                    jibun_address
                )

                # -------------------------------------------------
                # 검색 성공
                # -------------------------------------------------

                if lat and lon:

                    success_count += 1

                    lat_list.append(lat)
                    lon_list.append(lon)

                    # -------------------------------------------------
                    # 품목별 색상
                    # -------------------------------------------------

                    color = "blue"

                    if "건폐" in item:
                        color = "blue"

                    elif "빼기" in item:
                        color = "red"

                   

                    # -------------------------------------------------
                    # 팝업 내용
                    # -------------------------------------------------

                    popup_html = f"""
                    <div style="width:260px;">

                    <h4>폐기물 접수</h4>

                    <b>품명:</b> {item}<br>

                    <b>수량:</b> {qty}<br>

                    <b>연락처:</b> {phone}<br>

                    <b>도로명:</b> {road_address}<br>

                    <b>지번:</b> {jibun_address}<br>

                    <b>검색주소:</b> {final_address}

                    </div>
                    """

                    # -------------------------------------------------
                    # 마커 생성
                    # -------------------------------------------------

                    folium.Marker(
                        location=[lat, lon],
                        popup=folium.Popup(
                            popup_html,
                            max_width=300
                        ),
                        tooltip=item,
                        icon=folium.Icon(color=color)
                    ).add_to(marker_cluster)

                # -------------------------------------------------
                # 검색 실패
                # -------------------------------------------------

                else:

                    fail_count += 1

                    fail_addresses.append({
                        "도로명주소": road_address,
                        "지번주소": jibun_address
                    })

            except Exception as e:

                fail_count += 1

                fail_addresses.append({
                    "도로명주소": road_address,
                    "지번주소": jibun_address
                })

                st.warning(f"{idx+1}번째 오류: {e}")

            # 진행률 표시
            progress_bar.progress((idx + 1) / total_count)

        # =====================================================
        # 지도 중심 자동 계산
        # =====================================================

        if lat_list and lon_list:

            center_lat = sum(lat_list) / len(lat_list)
            center_lon = sum(lon_list) / len(lon_list)

            m.location = [center_lat, center_lon]

        # =====================================================
        # 결과 표시
        # =====================================================

        st.success("지도 생성 완료")

        col1, col2 = st.columns(2)

        with col1:
            st.metric("주소 검색 성공", success_count)

        with col2:
            st.metric("주소 검색 실패", fail_count)

        # =====================================================
        # 지도 출력
        # =====================================================

        st_folium(
            m,
            width=1400,
            height=700
        )

        # =====================================================
        # 품목별 집계
        # =====================================================

        st.subheader("품목별 집계")

        summary = (
            df.groupby("품명")["수량"]
            .sum()
            .reset_index()
        )

        st.dataframe(summary)

        # =====================================================
        # 실패 주소 목록
        # =====================================================

        if fail_addresses:

            st.subheader("주소 검색 실패 목록")

            fail_df = pd.DataFrame(fail_addresses)

            st.dataframe(fail_df)

    except Exception as e:

        st.error(f"오류 발생: {e}")
