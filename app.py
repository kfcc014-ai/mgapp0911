from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="MG 금융 데이터 CRUD 대시보드",
    page_icon="🏦",
    layout="wide",
)

st.markdown(
    """
    <style>
      .stApp { background: #f4f7f9; }
      .mg-header {
        background:#102a43; color:white; padding:18px 22px;
        border-radius:14px; margin-bottom:14px;
      }
      .mg-header h1 { margin:0; font-size:1.55rem; }
      .mg-header p { margin:.3rem 0 0; color:#c9e2f2; font-size:.9rem; }
      div[data-testid="stMetric"] {
        background:#fff; border:1px solid #dce5eb; border-radius:13px;
        padding:14px 16px; box-shadow:0 3px 12px rgba(22,43,59,.04);
      }
      div[data-testid="stDataFrame"] { border-radius:12px; overflow:hidden; }
      .small-note { color:#637789; font-size:.82rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="mg-header">
      <h1>MG 금융 데이터 CRUD 대시보드</h1>
      <p>Streamlit + Supabase · 조회 / 추가 / 수정 / 삭제</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Default Supabase connection
# -----------------------------
# Publishable key is intentionally embedded for this training app.
# Do NOT replace this with a service-role/secret key.
SUPABASE_REST_URL = "https://xrxnlyqpncpcmpfnuafr.supabase.co/rest/v1"
SUPABASE_KEY = "sb_publishable_2g8_0-OVbgjn5jBMMAd7XQ_r43C2nLE"
REQUEST_TIMEOUT = 20

DEFAULT_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Accept": "application/json",
}

if "flash" not in st.session_state:
    st.session_state.flash = None


def set_flash(kind: str, message: str) -> None:
    st.session_state.flash = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop("flash", None)
    if not item:
        return
    kind, message = item
    if kind == "success":
        st.success(message)
    elif kind == "warning":
        st.warning(message)
    else:
        st.error(message)

st.caption("Supabase 기본 연결 사용 중 · Publishable Key는 apikey 헤더로만 전송합니다.")
st.warning(
    "교육/실습용 설정입니다. 현재 Publishable/anon 역할에 쓰기 권한이 열려 있으면 이 앱을 접속할 수 있는 사용자도 데이터를 추가·수정·삭제할 수 있습니다."
)
show_flash()

# -----------------------------
# Data access helpers (Supabase REST API)
# -----------------------------
TABLE_PK = {
    "members": "member_id",
    "deposit_accounts": "account_id",
    "loans": "loan_id",
    "branches": "branch_id",
}


def rest_request(
    method: str,
    table: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    prefer: str | None = None,
) -> Any:
    headers = dict(DEFAULT_HEADERS)
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer

    url = f"{SUPABASE_REST_URL}/{table}"
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Supabase 요청 연결 오류: {exc}") from exc

    if not response.ok:
        detail = response.text.strip()
        try:
            body = response.json()
            detail = body.get("message") or body.get("details") or body.get("hint") or detail
        except Exception:
            pass
        raise RuntimeError(f"Supabase REST 요청 실패 ({response.status_code}): {detail}")

    if response.status_code == 204 or not response.text.strip():
        return None
    return response.json()


def fetch_all(table: str, order_by: str) -> list[dict[str, Any]]:
    """Fetch all rows in pages because Data API responses can be capped."""
    rows: list[dict[str, Any]] = []
    page_size = 1000
    offset = 0
    while True:
        batch = rest_request(
            "GET",
            table,
            params={
                "select": "*",
                "order": f"{order_by}.asc",
                "limit": page_size,
                "offset": offset,
            },
        ) or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def load_data() -> dict[str, list[dict[str, Any]]]:
    return {
        "members": fetch_all("members", "member_id"),
        "deposit_accounts": fetch_all("deposit_accounts", "account_id"),
        "loans": fetch_all("loans", "loan_id"),
        "branches": fetch_all("branches", "branch_id"),
    }


def get_next_id(table: str, pk: str) -> int:
    """Read the latest PK immediately before insert to avoid stale Streamlit state."""
    rows = rest_request(
        "GET",
        table,
        params={"select": pk, "order": f"{pk}.desc", "limit": 1},
    ) or []
    return int(rows[0][pk]) + 1 if rows else 1


def verify_row(table: str, pk: str, row_id: int) -> dict[str, Any]:
    rows = rest_request(
        "GET",
        table,
        params={"select": "*", pk: f"eq.{row_id}", "limit": 1},
    ) or []
    if not rows:
        raise RuntimeError(f"저장 요청 후 {table}.{pk}={row_id} 행을 재조회하지 못했습니다.")
    return rows[0]


def do_insert(table: str, payload: dict[str, Any]) -> None:
    pk = TABLE_PK[table]
    row_id = int(payload[pk])
    rest_request(
        "POST",
        table,
        payload=payload,
        prefer="return=representation",
    )
    verify_row(table, pk, row_id)


def do_update(table: str, pk: str, row_id: int, payload: dict[str, Any]) -> None:
    rest_request(
        "PATCH",
        table,
        params={pk: f"eq.{row_id}"},
        payload=payload,
        prefer="return=representation",
    )
    verify_row(table, pk, row_id)


def do_delete(table: str, pk: str, row_id: int) -> None:
    rest_request(
        "DELETE",
        table,
        params={pk: f"eq.{row_id}"},
        prefer="return=representation",
    )
    rows = rest_request(
        "GET",
        table,
        params={"select": pk, pk: f"eq.{row_id}", "limit": 1},
    ) or []
    if rows:
        raise RuntimeError(f"삭제 후에도 {table}.{pk}={row_id} 행이 남아 있습니다.")

try:
    with st.spinner("데이터를 불러오는 중입니다..."):
        data = load_data()
except Exception as exc:
    st.error(f"데이터 조회 실패: {exc}\n\n기본 Supabase 연결 정보와 GRANT/RLS 정책을 확인해 주세요.")
    st.stop()

members = data["members"]
accounts = data["deposit_accounts"]
loans = data["loans"]
branches = data["branches"]

branch_by_id = {int(b["branch_id"]): b for b in branches}
member_by_id = {int(m["member_id"]): m for m in members}


def branch_label(branch_id: int) -> str:
    b = branch_by_id.get(int(branch_id), {})
    return b.get("branch_name", f"지점 #{branch_id}")


def member_label(member_id: int) -> str:
    m = member_by_id.get(int(member_id), {})
    return f"{m.get('name', '조합원')} (#{member_id})"


def branch_options() -> list[int]:
    return [int(b["branch_id"]) for b in branches]


def member_options() -> list[int]:
    return [int(m["member_id"]) for m in members]


def money(value: Any) -> str:
    try:
        return f"{float(value):,.0f}원"
    except (TypeError, ValueError):
        return "0원"


# -----------------------------
# KPI + charts
# -----------------------------
deposit_total = sum(float(a.get("balance") or 0) for a in accounts)
active_loans = [l for l in loans if l.get("status") != "완제"]
loan_total = sum(float(l.get("loan_amount") or 0) for l in active_loans)
overdue_count = sum(1 for l in loans if l.get("status") == "연체")

m1, m2, m3, m4 = st.columns(4)
m1.metric("전체 조합원", f"{len(members):,}명")
m2.metric("예적금 총액", money(deposit_total))
m3.metric("대출 잔액", money(loan_total))
m4.metric("연체 대출", f"{overdue_count:,}건")

st.write("")
chart_left, chart_right = st.columns([1.05, 0.95])

with chart_left:
    st.subheader("지점별 예적금 잔액")
    branch_sums = []
    for b in branches:
        bid = int(b["branch_id"])
        total = sum(float(a.get("balance") or 0) for a in accounts if int(a.get("branch_id")) == bid)
        branch_sums.append({"지점": b["branch_name"], "예적금 잔액": total})
    branch_df = pd.DataFrame(branch_sums).sort_values("예적금 잔액", ascending=False) if branch_sums else pd.DataFrame(columns=["지점", "예적금 잔액"])
    if branch_df.empty:
        st.info("지점/예적금 데이터가 없습니다.")
    else:
        st.bar_chart(branch_df, x="지점", y="예적금 잔액", use_container_width=True)

with chart_right:
    st.subheader("대출 상태")
    status_counts: dict[str, int] = {}
    for loan in loans:
        status = str(loan.get("status") or "미지정")
        status_counts[status] = status_counts.get(status, 0) + 1
    status_df = pd.DataFrame([{"상태": k, "건수": v} for k, v in status_counts.items()])
    if status_df.empty:
        st.info("대출 데이터가 없습니다.")
    else:
        st.vega_lite_chart(
            status_df,
            {
                "mark": {"type": "arc", "innerRadius": 52, "tooltip": True},
                "encoding": {
                    "theta": {"field": "건수", "type": "quantitative"},
                    "color": {"field": "상태", "type": "nominal"},
                    "tooltip": [
                        {"field": "상태", "type": "nominal"},
                        {"field": "건수", "type": "quantitative"},
                    ],
                },
            },
            use_container_width=True,
        )

st.divider()
st.header("데이터 관리")
st.caption("각 메뉴에서 조회, 추가, 수정, 삭제를 수행할 수 있습니다. 변경 후 앱이 자동으로 다시 조회됩니다.")


# -----------------------------
# Shared view helpers
# -----------------------------
def dataframe_download(df: pd.DataFrame, filename: str, key: str) -> None:
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "CSV 다운로드",
        data=csv,
        file_name=filename,
        mime="text/csv",
        key=key,
    )


def filter_df(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query.strip() or df.empty:
        return df
    q = query.strip().lower()
    mask = df.astype(str).apply(lambda col: col.str.lower().str.contains(q, na=False)).any(axis=1)
    return df[mask]


def rerun_app() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def run_change(action, success_message: str) -> None:
    try:
        action()
        set_flash("success", success_message)
        rerun_app()
    except Exception as exc:
        st.error(f"작업 실패: {exc}")


# -----------------------------
# Members CRUD
# -----------------------------
def render_members() -> None:
    view, create, update, delete = st.tabs(["조회", "추가", "수정", "삭제"])

    display_rows = []
    for r in members:
        display_rows.append(
            {
                "조합원 ID": r["member_id"],
                "이름": r["name"],
                "생년월일": r["birth_date"],
                "성별": "여성" if r["gender"] == "F" else "남성" if r["gender"] == "M" else r["gender"],
                "가입일": r["join_date"],
                "지점": branch_label(r["branch_id"]),
                "전화번호": r["phone"],
            }
        )
    df = pd.DataFrame(display_rows)

    with view:
        q = st.text_input("조합원 검색", placeholder="이름, 전화번호, 지점 등", key="member_search")
        filtered = filter_df(df, q)
        st.caption(f"{len(filtered):,}건")
        st.dataframe(filtered, use_container_width=True, hide_index=True)
        dataframe_download(filtered, "members.csv", "download_members")

    with create:
        with st.form("member_create"):
            c1, c2 = st.columns(2)
            name = c1.text_input("이름*")
            birth_date = c2.date_input("생년월일*", value=date(1990, 1, 1))
            gender = c1.selectbox("성별*", ["F", "M"], format_func=lambda x: "여성(F)" if x == "F" else "남성(M)")
            join_date = c2.date_input("가입일*", value=date.today())
            bids = branch_options()
            branch_id = c1.selectbox("지점*", bids, format_func=branch_label) if bids else None
            phone = c2.text_input("전화번호*", placeholder="010-0000-0000")
            submit = st.form_submit_button("조합원 추가", type="primary")
        if submit:
            if not name.strip() or not phone.strip() or branch_id is None:
                st.error("필수값을 입력해 주세요.")
            else:
                payload = {
                    "member_id": get_next_id("members", "member_id"),
                    "name": name.strip(),
                    "birth_date": birth_date.isoformat(),
                    "gender": gender,
                    "join_date": join_date.isoformat(),
                    "branch_id": int(branch_id),
                    "phone": phone.strip(),
                }
                run_change(lambda: do_insert("members", payload), f"조합원 #{payload['member_id']}을 추가했습니다.")

    with update:
        ids = member_options()
        if not ids:
            st.info("수정할 조합원이 없습니다.")
        else:
            selected = st.selectbox("수정할 조합원", ids, format_func=member_label, key="member_edit_id")
            row = member_by_id[selected]
            key_suffix = str(selected)
            with st.form(f"member_update_{selected}"):
                c1, c2 = st.columns(2)
                name = c1.text_input("이름*", value=row["name"], key=f"member_name_{key_suffix}")
                birth_date = c2.date_input("생년월일*", value=date.fromisoformat(row["birth_date"]), key=f"member_birth_{key_suffix}")
                gender_index = 0 if row["gender"] == "F" else 1
                gender = c1.selectbox("성별*", ["F", "M"], index=gender_index, format_func=lambda x: "여성(F)" if x == "F" else "남성(M)", key=f"member_gender_{key_suffix}")
                join_date = c2.date_input("가입일*", value=date.fromisoformat(row["join_date"]), key=f"member_join_{key_suffix}")
                bids = branch_options()
                branch_idx = bids.index(int(row["branch_id"])) if int(row["branch_id"]) in bids else 0
                branch_id = c1.selectbox("지점*", bids, index=branch_idx, format_func=branch_label, key=f"member_branch_{key_suffix}")
                phone = c2.text_input("전화번호*", value=row["phone"], key=f"member_phone_{key_suffix}")
                submit = st.form_submit_button("수정 저장", type="primary")
            if submit:
                payload = {
                    "name": name.strip(),
                    "birth_date": birth_date.isoformat(),
                    "gender": gender,
                    "join_date": join_date.isoformat(),
                    "branch_id": int(branch_id),
                    "phone": phone.strip(),
                }
                run_change(lambda: do_update("members", "member_id", selected, payload), f"조합원 #{selected}을 수정했습니다.")

    with delete:
        ids = member_options()
        if not ids:
            st.info("삭제할 조합원이 없습니다.")
        else:
            selected = st.selectbox("삭제할 조합원", ids, format_func=member_label, key="member_delete_id")
            account_count = sum(1 for a in accounts if int(a["member_id"]) == selected)
            loan_count = sum(1 for l in loans if int(l["member_id"]) == selected)
            st.warning(f"연결 데이터: 예적금 {account_count}건 · 대출 {loan_count}건. 연결 데이터가 있으면 외래키 제약으로 삭제가 실패할 수 있습니다.")
            confirm = st.checkbox("삭제 내용을 확인했습니다.", key="member_delete_confirm")
            if st.button("조합원 삭제", type="primary", disabled=not confirm, key="member_delete_btn"):
                run_change(lambda: do_delete("members", "member_id", selected), f"조합원 #{selected}을 삭제했습니다.")


# -----------------------------
# Deposit accounts CRUD
# -----------------------------
def render_accounts() -> None:
    view, create, update, delete = st.tabs(["조회", "추가", "수정", "삭제"])
    account_types = ["보통예금", "정기예금", "정기적금", "자유적금"]

    display_rows = []
    for r in accounts:
        display_rows.append(
            {
                "계좌 ID": r["account_id"],
                "조합원": member_label(r["member_id"]),
                "지점": branch_label(r["branch_id"]),
                "계좌 종류": r["account_type"],
                "개설일": r["open_date"],
                "잔액": float(r["balance"]),
                "금리(%)": float(r["interest_rate"]),
            }
        )
    df = pd.DataFrame(display_rows)

    with view:
        q = st.text_input("예적금 계좌 검색", placeholder="조합원, 지점, 계좌 종류 등", key="account_search")
        filtered = filter_df(df, q)
        st.caption(f"{len(filtered):,}건")
        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True,
            column_config={
                "잔액": st.column_config.NumberColumn(format="%,.0f원"),
                "금리(%)": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )
        dataframe_download(filtered, "deposit_accounts.csv", "download_accounts")

    with create:
        mids = member_options()
        if not mids:
            st.info("먼저 조합원을 등록해 주세요.")
        else:
            with st.form("account_create"):
                c1, c2 = st.columns(2)
                member_id = c1.selectbox("조합원*", mids, format_func=member_label)
                derived_branch = int(member_by_id[member_id]["branch_id"])
                c2.text_input("지점", value=branch_label(derived_branch), disabled=True)
                account_type = c1.selectbox("계좌 종류*", account_types)
                open_date = c2.date_input("개설일*", value=date.today())
                balance = c1.number_input("잔액(원)*", min_value=0.0, step=100000.0, format="%.0f")
                interest_rate = c2.number_input("금리(%)*", min_value=0.0, step=0.01, format="%.2f")
                submit = st.form_submit_button("계좌 추가", type="primary")
            if submit:
                payload = {
                    "account_id": get_next_id("deposit_accounts", "account_id"),
                    "member_id": int(member_id),
                    "branch_id": derived_branch,
                    "account_type": account_type,
                    "open_date": open_date.isoformat(),
                    "balance": float(balance),
                    "interest_rate": float(interest_rate),
                }
                run_change(lambda: do_insert("deposit_accounts", payload), f"예적금 계좌 #{payload['account_id']}을 추가했습니다.")

    with update:
        ids = [int(a["account_id"]) for a in accounts]
        if not ids:
            st.info("수정할 예적금 계좌가 없습니다.")
        else:
            selected = st.selectbox("수정할 계좌", ids, format_func=lambda x: f"계좌 #{x}", key="account_edit_id")
            row = next(a for a in accounts if int(a["account_id"]) == selected)
            mids = member_options()
            with st.form(f"account_update_{selected}"):
                c1, c2 = st.columns(2)
                mid_idx = mids.index(int(row["member_id"])) if int(row["member_id"]) in mids else 0
                member_id = c1.selectbox("조합원*", mids, index=mid_idx, format_func=member_label, key=f"account_member_{selected}")
                derived_branch = int(member_by_id[member_id]["branch_id"])
                c2.text_input("지점", value=branch_label(derived_branch), disabled=True, key=f"account_branch_{selected}")
                type_idx = account_types.index(row["account_type"]) if row["account_type"] in account_types else 0
                account_type = c1.selectbox("계좌 종류*", account_types, index=type_idx, key=f"account_type_{selected}")
                open_date = c2.date_input("개설일*", value=date.fromisoformat(row["open_date"]), key=f"account_open_{selected}")
                balance = c1.number_input("잔액(원)*", min_value=0.0, value=float(row["balance"]), step=100000.0, format="%.0f", key=f"account_balance_{selected}")
                interest_rate = c2.number_input("금리(%)*", min_value=0.0, value=float(row["interest_rate"]), step=0.01, format="%.2f", key=f"account_rate_{selected}")
                submit = st.form_submit_button("수정 저장", type="primary")
            if submit:
                payload = {
                    "member_id": int(member_id),
                    "branch_id": derived_branch,
                    "account_type": account_type,
                    "open_date": open_date.isoformat(),
                    "balance": float(balance),
                    "interest_rate": float(interest_rate),
                }
                run_change(lambda: do_update("deposit_accounts", "account_id", selected, payload), f"예적금 계좌 #{selected}을 수정했습니다.")

    with delete:
        ids = [int(a["account_id"]) for a in accounts]
        if not ids:
            st.info("삭제할 예적금 계좌가 없습니다.")
        else:
            selected = st.selectbox("삭제할 계좌", ids, format_func=lambda x: f"계좌 #{x}", key="account_delete_id")
            row = next(a for a in accounts if int(a["account_id"]) == selected)
            st.write(f"조합원: **{member_label(row['member_id'])}** · 잔액: **{money(row['balance'])}** · 종류: **{row['account_type']}**")
            confirm = st.checkbox("삭제 내용을 확인했습니다.", key="account_delete_confirm")
            if st.button("계좌 삭제", type="primary", disabled=not confirm, key="account_delete_btn"):
                run_change(lambda: do_delete("deposit_accounts", "account_id", selected), f"예적금 계좌 #{selected}을 삭제했습니다.")


# -----------------------------
# Loans CRUD
# -----------------------------
def render_loans() -> None:
    view, create, update, delete = st.tabs(["조회", "추가", "수정", "삭제"])
    loan_statuses = ["정상", "연체", "완제"]
    loan_types = ["신용대출", "담보대출", "전세자금대출"]

    display_rows = []
    for r in loans:
        display_rows.append(
            {
                "대출 ID": r["loan_id"],
                "조합원": member_label(r["member_id"]),
                "지점": branch_label(r["branch_id"]),
                "대출 종류": r["loan_type"],
                "대출금액": float(r["loan_amount"]),
                "금리(%)": float(r["interest_rate"]),
                "시작일": r["start_date"],
                "만기일": r["due_date"],
                "상태": r["status"],
            }
        )
    df = pd.DataFrame(display_rows)

    with view:
        q = st.text_input("대출 검색", placeholder="조합원, 지점, 대출 종류, 상태 등", key="loan_search")
        filtered = filter_df(df, q)
        st.caption(f"{len(filtered):,}건")
        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True,
            column_config={
                "대출금액": st.column_config.NumberColumn(format="%,.0f원"),
                "금리(%)": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )
        dataframe_download(filtered, "loans.csv", "download_loans")

    with create:
        mids = member_options()
        if not mids:
            st.info("먼저 조합원을 등록해 주세요.")
        else:
            with st.form("loan_create"):
                c1, c2 = st.columns(2)
                member_id = c1.selectbox("조합원*", mids, format_func=member_label)
                derived_branch = int(member_by_id[member_id]["branch_id"])
                c2.text_input("지점", value=branch_label(derived_branch), disabled=True)
                loan_type = c1.selectbox("대출 종류*", loan_types)
                status = c2.selectbox("상태*", loan_statuses)
                loan_amount = c1.number_input("대출금액(원)*", min_value=0.0, step=1000000.0, format="%.0f")
                interest_rate = c2.number_input("금리(%)*", min_value=0.0, step=0.01, format="%.2f")
                start_date = c1.date_input("시작일*", value=date.today())
                due_date = c2.date_input("만기일*", value=date.today())
                submit = st.form_submit_button("대출 추가", type="primary")
            if submit:
                if due_date < start_date:
                    st.error("만기일은 시작일보다 빠를 수 없습니다.")
                else:
                    payload = {
                        "loan_id": get_next_id("loans", "loan_id"),
                        "member_id": int(member_id),
                        "branch_id": derived_branch,
                        "loan_type": loan_type,
                        "loan_amount": float(loan_amount),
                        "interest_rate": float(interest_rate),
                        "start_date": start_date.isoformat(),
                        "due_date": due_date.isoformat(),
                        "status": status,
                    }
                    run_change(lambda: do_insert("loans", payload), f"대출 #{payload['loan_id']}을 추가했습니다.")

    with update:
        ids = [int(l["loan_id"]) for l in loans]
        if not ids:
            st.info("수정할 대출이 없습니다.")
        else:
            selected = st.selectbox("수정할 대출", ids, format_func=lambda x: f"대출 #{x}", key="loan_edit_id")
            row = next(l for l in loans if int(l["loan_id"]) == selected)
            mids = member_options()
            with st.form(f"loan_update_{selected}"):
                c1, c2 = st.columns(2)
                mid_idx = mids.index(int(row["member_id"])) if int(row["member_id"]) in mids else 0
                member_id = c1.selectbox("조합원*", mids, index=mid_idx, format_func=member_label, key=f"loan_member_{selected}")
                derived_branch = int(member_by_id[member_id]["branch_id"])
                c2.text_input("지점", value=branch_label(derived_branch), disabled=True, key=f"loan_branch_{selected}")
                type_idx = loan_types.index(row["loan_type"]) if row["loan_type"] in loan_types else 0
                loan_type = c1.selectbox("대출 종류*", loan_types, index=type_idx, key=f"loan_type_{selected}")
                status_idx = loan_statuses.index(row["status"]) if row["status"] in loan_statuses else 0
                status = c2.selectbox("상태*", loan_statuses, index=status_idx, key=f"loan_status_{selected}")
                loan_amount = c1.number_input("대출금액(원)*", min_value=0.0, value=float(row["loan_amount"]), step=1000000.0, format="%.0f", key=f"loan_amount_{selected}")
                interest_rate = c2.number_input("금리(%)*", min_value=0.0, value=float(row["interest_rate"]), step=0.01, format="%.2f", key=f"loan_rate_{selected}")
                start_date = c1.date_input("시작일*", value=date.fromisoformat(row["start_date"]), key=f"loan_start_{selected}")
                due_date = c2.date_input("만기일*", value=date.fromisoformat(row["due_date"]), key=f"loan_due_{selected}")
                submit = st.form_submit_button("수정 저장", type="primary")
            if submit:
                if due_date < start_date:
                    st.error("만기일은 시작일보다 빠를 수 없습니다.")
                else:
                    payload = {
                        "member_id": int(member_id),
                        "branch_id": derived_branch,
                        "loan_type": loan_type,
                        "loan_amount": float(loan_amount),
                        "interest_rate": float(interest_rate),
                        "start_date": start_date.isoformat(),
                        "due_date": due_date.isoformat(),
                        "status": status,
                    }
                    run_change(lambda: do_update("loans", "loan_id", selected, payload), f"대출 #{selected}을 수정했습니다.")

    with delete:
        ids = [int(l["loan_id"]) for l in loans]
        if not ids:
            st.info("삭제할 대출이 없습니다.")
        else:
            selected = st.selectbox("삭제할 대출", ids, format_func=lambda x: f"대출 #{x}", key="loan_delete_id")
            row = next(l for l in loans if int(l["loan_id"]) == selected)
            st.write(f"조합원: **{member_label(row['member_id'])}** · 대출금액: **{money(row['loan_amount'])}** · 상태: **{row['status']}**")
            confirm = st.checkbox("삭제 내용을 확인했습니다.", key="loan_delete_confirm")
            if st.button("대출 삭제", type="primary", disabled=not confirm, key="loan_delete_btn"):
                run_change(lambda: do_delete("loans", "loan_id", selected), f"대출 #{selected}을 삭제했습니다.")


# -----------------------------
# Branches CRUD
# -----------------------------
def render_branches() -> None:
    view, create, update, delete = st.tabs(["조회", "추가", "수정", "삭제"])

    df = pd.DataFrame(
        [
            {
                "지점 ID": r["branch_id"],
                "지점명": r["branch_name"],
                "지역": r["region"],
                "담당자": r["manager_name"],
            }
            for r in branches
        ]
    )

    with view:
        q = st.text_input("지점 검색", placeholder="지점명, 지역, 담당자", key="branch_search")
        filtered = filter_df(df, q)
        st.caption(f"{len(filtered):,}건")
        st.dataframe(filtered, use_container_width=True, hide_index=True)
        dataframe_download(filtered, "branches.csv", "download_branches")

    with create:
        with st.form("branch_create"):
            c1, c2 = st.columns(2)
            branch_name = c1.text_input("지점명*")
            region = c2.text_input("지역*")
            manager_name = c1.text_input("담당자*")
            submit = st.form_submit_button("지점 추가", type="primary")
        if submit:
            if not all([branch_name.strip(), region.strip(), manager_name.strip()]):
                st.error("필수값을 입력해 주세요.")
            else:
                payload = {
                    "branch_id": get_next_id("branches", "branch_id"),
                    "branch_name": branch_name.strip(),
                    "region": region.strip(),
                    "manager_name": manager_name.strip(),
                }
                run_change(lambda: do_insert("branches", payload), f"지점 #{payload['branch_id']}을 추가했습니다.")

    with update:
        ids = branch_options()
        if not ids:
            st.info("수정할 지점이 없습니다.")
        else:
            selected = st.selectbox("수정할 지점", ids, format_func=branch_label, key="branch_edit_id")
            row = branch_by_id[selected]
            with st.form(f"branch_update_{selected}"):
                c1, c2 = st.columns(2)
                branch_name = c1.text_input("지점명*", value=row["branch_name"], key=f"branch_name_{selected}")
                region = c2.text_input("지역*", value=row["region"], key=f"branch_region_{selected}")
                manager_name = c1.text_input("담당자*", value=row["manager_name"], key=f"branch_manager_{selected}")
                submit = st.form_submit_button("수정 저장", type="primary")
            if submit:
                payload = {
                    "branch_name": branch_name.strip(),
                    "region": region.strip(),
                    "manager_name": manager_name.strip(),
                }
                run_change(lambda: do_update("branches", "branch_id", selected, payload), f"지점 #{selected}을 수정했습니다.")

    with delete:
        ids = branch_options()
        if not ids:
            st.info("삭제할 지점이 없습니다.")
        else:
            selected = st.selectbox("삭제할 지점", ids, format_func=branch_label, key="branch_delete_id")
            member_count = sum(1 for m in members if int(m["branch_id"]) == selected)
            account_count = sum(1 for a in accounts if int(a["branch_id"]) == selected)
            loan_count = sum(1 for l in loans if int(l["branch_id"]) == selected)
            st.warning(
                f"연결 데이터: 조합원 {member_count}건 · 예적금 {account_count}건 · 대출 {loan_count}건. "
                "연결 데이터가 있으면 외래키 제약으로 삭제가 실패할 수 있습니다."
            )
            confirm = st.checkbox("삭제 내용을 확인했습니다.", key="branch_delete_confirm")
            if st.button("지점 삭제", type="primary", disabled=not confirm, key="branch_delete_btn"):
                run_change(lambda: do_delete("branches", "branch_id", selected), f"지점 #{selected}을 삭제했습니다.")


main_tabs = st.tabs(["👤 조합원", "💰 예적금 계좌", "🏦 대출", "🏢 지점"])
with main_tabs[0]:
    render_members()
with main_tabs[1]:
    render_accounts()
with main_tabs[2]:
    render_loans()
with main_tabs[3]:
    render_branches()

st.divider()
if st.button("🔄 전체 새로고침"):
    rerun_app()

st.caption(
    "보안 안내: 코드에는 Publishable key만 사용했습니다. 현재처럼 anon CRUD 권한을 허용한 상태로 공개 배포하지 않는 것을 권장합니다."
)
