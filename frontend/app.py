"""Streamlit Frontend Application - Portfolio Currency Converter."""

import os
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]
import plotly.graph_objects as go  # type: ignore[import-untyped]
import streamlit as st

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frontend.api_client import BackendAPIClient

# Currency symbols and country flags dictionary
CURRENCY_FLAGS: dict[str, str] = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "JPY": "🇯🇵",
    "INR": "🇮🇳",
    "CAD": "🇨🇦",
    "AUD": "🇦🇺",
    "CHF": "🇨🇭",
    "CNY": "🇨🇳",
    "BRL": "🇧🇷",
    "MXN": "🇲🇽",
    "KRW": "🇰🇷",
    "SGD": "🇸🇬",
    "HKD": "🇭🇰",
    "NZD": "🇳🇿",
    "SEK": "🇸🇪",
    "NOK": "🇳🇴",
    "DKK": "🇩🇰",
    "PLN": "🇵🇱",
    "TRY": "🇹🇷",
    "ZAR": "🇿🇦",
    "ILS": "🇮🇱",
    "HUF": "🇭🇺",
    "CZK": "🇨🇿",
    "RON": "🇷🇴",
    "PHP": "🇵🇭",
    "IDR": "🇮🇩",
    "MYR": "🇲🇾",
    "THB": "🇹🇭",
    "ISK": "🇮🇸",
    "KWD": "🇰🇼",
    "BHD": "🇧🇭",
    "OMR": "🇴🇲",
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "INR": "₹",
    "CAD": "CA$",
    "AUD": "A$",
    "CHF": "CHF",
    "CNY": "¥",
    "KRW": "₩",
    "BRL": "R$",
    "MXN": "MX$",
    "SGD": "S$",
    "HKD": "HK$",
    "KWD": "KD",
}

st.set_page_config(
    page_title="Currency Converter | Industry Grade",
    page_icon="💱",
    layout="wide",
)

st.title("💱 Currency Converter")
st.caption(
    "Portfolio-Quality Financial Application | Decimal Engine + SQLite + FastAPI"
)

# Initialize Backend API Client
backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
client = BackendAPIClient(base_url=backend_url)

# Session State Initialization
if "session_id" not in st.session_state:
    st.session_state["session_id"] = uuid.uuid4().hex[:16]

if "default_base" not in st.session_state:
    st.session_state["default_base"] = "USD"

if "number_format" not in st.session_state:
    st.session_state["number_format"] = "US (1,234.56)"

if "rounding_policy" not in st.session_state:
    st.session_state["rounding_policy"] = "ROUND_HALF_UP"


def format_money_str(amount_str: str) -> str:
    """Format string amount according to chosen number format preference."""
    if st.session_state.get("number_format") == "EU (1.234,56)":
        if "." in amount_str:
            parts = amount_str.split(".")
            int_part = parts[0].replace(",", "")
            dec_part = parts[1]
            try:
                formatted_int = f"{int(int_part):,}".replace(",", ".")
                return f"{formatted_int},{dec_part}"
            except ValueError:
                return amount_str.replace(".", ",")
        return amount_str
    return amount_str


# Sidebar
with st.sidebar:
    st.header("⚙️ System Status")
    st.write(f"**Backend Endpoint:** `{backend_url}`")

    health_res = client.get_health()
    if health_res.get("success"):
        st.success("🟢 Backend Connected & Healthy")
        v = health_res.get("data", {}).get("version", "0.1.0")
        env = health_res.get("data", {}).get("environment", "development")
        st.caption(f"API Version: v{v} ({env})")
    else:
        st.error("🔴 Backend Unreachable")
        st.caption("Ensure Uvicorn backend is running on port 8000.")

    st.markdown("---")
    st.markdown("### 👤 Session Identity")
    st.caption(f"Anonymous Session ID: `{st.session_state['session_id']}`")

    st.markdown("---")
    st.markdown("### ℹ️ Provider Reality")
    st.info(
        "**Indicative Reference Rates:** Rates are sourced from European Central Bank (ECB) "
        "reference data (typically updated once per business day). These are indicative reference "
        "rates, not executable trading quotes."
    )


# Fetch supported currencies from backend
@st.cache_data(ttl=300)
def fetch_currencies() -> list[dict[str, Any]]:
    res = client.get_currencies()
    if res.get("success") and res.get("data"):
        return res["data"].get("currencies", [])  # type: ignore[no-any-return]
    return []


currency_items = fetch_currencies()

if not currency_items:
    st.error(
        "⚠️ Unable to load supported currencies from backend. Please ensure the backend is running."
    )
    st.code(
        "./.venv/bin/uvicorn app.main:app --app-dir backend --port 8000",
        language="bash",
    )
    st.stop()

# Build currency selection options
currency_codes = [c["code"] for c in currency_items]
currency_labels = {
    c[
        "code"
    ]: f"{CURRENCY_FLAGS.get(c['code'], '🌐')} {c['code']} - {c['name']} ({CURRENCY_SYMBOLS.get(c['code'], '')})"
    for c in currency_items
}

if "from_currency" not in st.session_state:
    st.session_state["from_currency"] = (
        st.session_state["default_base"]
        if st.session_state["default_base"] in currency_codes
        else currency_codes[0]
    )
if "to_currency" not in st.session_state:
    st.session_state["to_currency"] = (
        "EUR" if "EUR" in currency_codes else currency_codes[1]
    )


def swap_currencies() -> None:
    temp = st.session_state["from_currency"]
    st.session_state["from_currency"] = st.session_state["to_currency"]
    st.session_state["to_currency"] = temp


# Main Application Navigation Tabs
(
    tab_convert,
    tab_reverse,
    tab_multi,
    tab_charts,
    tab_history,
    tab_explorer,
    tab_settings,
) = st.tabs(
    [
        "🔄 Convert Currency",
        "↩️ Reverse Conversion",
        "📊 Multi-Currency Table",
        "📈 Historical & Trends",
        "🕒 Conversion History",
        "🧭 Currency Explorer",
        "⚙️ Settings",
    ]
)

# -----------------------------------------------------------------------------
# TAB 1: MAIN CONVERTER
# -----------------------------------------------------------------------------
with tab_convert:
    # Quick Favorites Bar
    fav_res = client.get_favorites(st.session_state["session_id"])
    fav_codes: list[str] = []
    if fav_res.get("success") and fav_res.get("data"):
        fav_codes = [f["code"] for f in fav_res["data"].get("favorites", [])]

    if not fav_codes:
        fav_codes = ["USD", "EUR", "GBP", "JPY", "INR"]

    st.markdown("##### ⭐ Quick Select Favorites")
    quick_cols = st.columns(len(fav_codes) + 1)
    for idx, f_code in enumerate(fav_codes):
        with quick_cols[idx]:
            flag = CURRENCY_FLAGS.get(f_code, "🌐")
            if st.button(
                f"{flag} {f_code}", key=f"quick_fav_{f_code}", use_container_width=True
            ):
                st.session_state["to_currency"] = f_code
                st.rerun()

    st.markdown("---")

    col_from, col_swap, col_to = st.columns([5, 1, 5], vertical_alignment="bottom")

    with col_from:
        from_idx = (
            currency_codes.index(st.session_state["from_currency"])
            if st.session_state["from_currency"] in currency_codes
            else 0
        )
        selected_from = st.selectbox(
            "From Currency",
            options=currency_codes,
            format_func=lambda x: currency_labels.get(x, x),
            index=from_idx,
            key="from_select",
        )
        st.session_state["from_currency"] = selected_from

    with col_swap:
        st.button(
            "⇄",
            on_click=swap_currencies,
            help="Swap From and To currencies",
            use_container_width=True,
        )

    with col_to:
        to_idx = (
            currency_codes.index(st.session_state["to_currency"])
            if st.session_state["to_currency"] in currency_codes
            else 1
        )
        selected_to = st.selectbox(
            "To Currency",
            options=currency_codes,
            format_func=lambda x: currency_labels.get(x, x),
            index=to_idx,
            key="to_select",
        )
        st.session_state["to_currency"] = selected_to

    # Favorite Toggle for Target Currency
    is_target_fav = selected_to in fav_codes
    fav_col1, fav_col2 = st.columns([1, 4])
    with fav_col1:
        if is_target_fav:
            if st.button(
                f"⭐ In Favorites ({selected_to})",
                help="Click to remove from favorites",
            ):
                client.remove_favorite(st.session_state["session_id"], selected_to)
                st.rerun()
        else:
            if st.button(f"☆ Add {selected_to} to Favorites"):
                client.add_favorite(st.session_state["session_id"], selected_to)
                st.rerun()

    # Amount Input
    amount_input = st.text_input(
        "Amount to Convert",
        value="100.00",
        help="Enter a positive decimal amount (e.g. 100.50 or 1,000.50).",
    )

    if amount_input:
        with st.spinner("Fetching rate and calculating with Decimal engine..."):
            conv_res = client.convert(
                from_currency=st.session_state["from_currency"],
                to_currency=st.session_state["to_currency"],
                amount=amount_input,
                session_id=st.session_state["session_id"],
            )

        if conv_res.get("success"):
            data = conv_res.get("data", {})
            meta = conv_res.get("meta", {})

            converted_amt = data.get("converted_amount", "0")
            rate_val = data.get("rate", "0")
            inverse_rate = data.get("inverse_rate", "0")
            target_minor = data.get("target_minor_units", 2)
            from_curr = data.get("from", st.session_state["from_currency"])
            to_curr = data.get("to", st.session_state["to_currency"])

            from_sym = CURRENCY_SYMBOLS.get(from_curr, from_curr)
            to_sym = CURRENCY_SYMBOLS.get(to_curr, to_curr)

            st.markdown(
                f"""
                <div style="background-color: #f0f7ff; padding: 24px; border-radius: 12px; border: 1px solid #cce4ff; margin: 16px 0;">
                    <div style="font-size: 14px; color: #555;">{from_curr} to {to_curr} Conversion</div>
                    <div style="font-size: 32px; font-weight: 700; color: #1a1a1a; margin: 8px 0;">
                        {to_sym} {format_money_str(converted_amt)} <span style="font-size: 20px; font-weight: 500; color: #666;">{to_curr}</span>
                    </div>
                    <div style="font-size: 15px; color: #444;">
                        <b>Input:</b> {from_sym} {format_money_str(amount_input)} {from_curr}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Metadata details row
            r_col1, r_col2, r_col3 = st.columns(3)
            with r_col1:
                st.caption(f"**Direct Rate:** 1 {from_curr} = {rate_val} {to_curr}")
            with r_col2:
                st.caption(
                    f"**Inverse Rate:** 1 {to_curr} = {inverse_rate} {from_curr}"
                )
            with r_col3:
                st.caption(f"**Target Minor Units:** {target_minor} decimals")

            # Provider status and staleness warnings
            provider_name = meta.get("provider", "unknown").capitalize()
            rate_date = meta.get("rate_date", "N/A")
            is_stale = meta.get("stale", False)
            age_sec = meta.get("age_seconds", 0)

            st.info(f"Source: **{provider_name}** | Rates as of: **{rate_date}**")

            if is_stale:
                st.warning(
                    f"⚠️ **Stale Rate Serving:** Upstream providers are experiencing latency. "
                    f"This rate is served from cached data (age: {age_sec}s)."
                )

            with st.expander("🔍 View Raw API Envelope"):
                st.json(conv_res)

        else:
            err = conv_res.get("error", {})
            st.error("❌ Conversion Failed")
            st.warning(
                f"**[{err.get('code', 'ERROR')}]:** {err.get('message', 'An error occurred.')}"
            )

# -----------------------------------------------------------------------------
# TAB 2: REVERSE TARGET CONVERSION
# -----------------------------------------------------------------------------
with tab_reverse:
    st.markdown(
        "##### Calculate how much source currency is needed to obtain a target sum."
    )

    col_rev_from, col_rev_to = st.columns(2)
    with col_rev_from:
        rev_from = st.selectbox(
            "I want to pay with",
            options=currency_codes,
            format_func=lambda x: currency_labels.get(x, x),
            index=currency_codes.index("USD") if "USD" in currency_codes else 0,
            key="rev_from_select",
        )
    with col_rev_to:
        rev_to = st.selectbox(
            "To receive exactly",
            options=currency_codes,
            format_func=lambda x: currency_labels.get(x, x),
            index=currency_codes.index("INR") if "INR" in currency_codes else 1,
            key="rev_to_select",
        )

    target_amount_input = st.text_input(
        f"Desired Target Amount in {rev_to}",
        value="10000",
        help="How much target currency you want to receive.",
    )

    if st.button("Calculate Required Amount", type="primary", use_container_width=True):
        with st.spinner("Calculating required payment with Decimal engine..."):
            rev_res = client.reverse_convert(
                from_currency=rev_from,
                to_currency=rev_to,
                target_amount=target_amount_input,
            )

        if rev_res.get("success"):
            rev_data = rev_res.get("data", {})
            rev_meta = rev_res.get("meta", {})

            req_amt = rev_data.get("required_from_amount")
            tgt_amt = rev_data.get("target_amount")
            rev_rate = rev_data.get("rate")

            st.success(
                f"💵 To receive **{tgt_amt} {rev_to}**, you need to pay "
                f"**{req_amt} {rev_from}** (applied rate: {rev_rate})."
            )
            st.caption(
                f"Source: {rev_meta.get('provider', '').capitalize()} | Rates as of: {rev_meta.get('rate_date', '')}"
            )

            with st.expander("🔍 View Raw Envelope"):
                st.json(rev_res)
        else:
            err = rev_res.get("error", {})
            st.error(
                f"**[{err.get('code', 'ERROR')}]:** {err.get('message', 'Reverse conversion failed.')}"
            )

# -----------------------------------------------------------------------------
# TAB 3: MULTI-CURRENCY TABLE
# -----------------------------------------------------------------------------
with tab_multi:
    st.markdown("##### Convert a Base Amount Across Multiple Currencies Simultaneously")

    m_col1, m_col2 = st.columns([1, 1])
    with m_col1:
        multi_base = st.selectbox(
            "Base Currency",
            options=currency_codes,
            format_func=lambda x: currency_labels.get(x, x),
            index=currency_codes.index("USD") if "USD" in currency_codes else 0,
            key="multi_base_select",
        )
    with m_col2:
        multi_amount_str = st.text_input(
            "Base Amount", value="100.00", key="multi_amount_input"
        )

    try:
        base_amt_dec = Decimal(multi_amount_str.replace(",", ""))
    except (ValueError, ArithmeticError):
        base_amt_dec = Decimal("100.00")

    # Fetch latest rates for this base
    rates_res = client.get_rates(base=multi_base)
    if rates_res.get("success") and rates_res.get("data"):
        raw_rates = rates_res["data"].get("rates", {})
        table_rows: list[dict[str, Any]] = []

        # List currencies, giving priority to favorites
        display_targets = fav_codes + [
            c
            for c in ["EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "INR", "CNY"]
            if c not in fav_codes
        ]

        for t_code in display_targets:
            if t_code == multi_base:
                rate_dec = Decimal("1.0")
            elif t_code in raw_rates:
                rate_dec = Decimal(str(raw_rates[t_code]))
            else:
                continue

            converted_val = base_amt_dec * rate_dec
            minor = 0 if t_code == "JPY" else 2
            formatted_val = f"{converted_val:.{minor}f}"

            table_rows.append(
                {
                    "Favorite": "⭐" if t_code in fav_codes else "",
                    "Flag": CURRENCY_FLAGS.get(t_code, "🌐"),
                    "Currency": t_code,
                    "Exchange Rate": f"{rate_dec:.6f}",
                    f"Converted ({t_code})": format_money_str(formatted_val),
                }
            )

        if table_rows:
            df_multi = pd.DataFrame(table_rows)
            st.dataframe(df_multi, use_container_width=True, hide_index=True)
            st.caption(
                f"Source: {rates_res.get('meta', {}).get('provider', '').capitalize()} | "
                f"Rates as of: {rates_res.get('data', {}).get('rate_date', '')}"
            )
    else:
        st.warning("Could not fetch multi-currency rates from backend.")

# -----------------------------------------------------------------------------
# TAB 4: HISTORICAL & TRENDS
# -----------------------------------------------------------------------------
with tab_charts:
    st.markdown("##### Historical Exchange Rates & Statistical Trend Analysis")

    c_hist_from, c_hist_to, c_range = st.columns([3, 3, 4])
    with c_hist_from:
        hist_base = st.selectbox(
            "Base Currency",
            options=currency_codes,
            format_func=lambda x: currency_labels.get(x, x),
            index=currency_codes.index("USD") if "USD" in currency_codes else 0,
            key="hist_base_select",
        )
    with c_hist_to:
        hist_target = st.selectbox(
            "Target Currency",
            options=currency_codes,
            format_func=lambda x: currency_labels.get(x, x),
            index=currency_codes.index("EUR") if "EUR" in currency_codes else 1,
            key="hist_target_select",
        )
    with c_range:
        range_option = st.selectbox(
            "Time Horizon",
            options=["7D", "1M", "3M", "6M", "1Y", "5Y", "Custom"],
            index=1,
            help="Select historical reference time window.",
        )

    today = date.today()
    if range_option == "7D":
        start_d = today - timedelta(days=7)
        end_d = today
    elif range_option == "1M":
        start_d = today - timedelta(days=30)
        end_d = today
    elif range_option == "3M":
        start_d = today - timedelta(days=90)
        end_d = today
    elif range_option == "6M":
        start_d = today - timedelta(days=180)
        end_d = today
    elif range_option == "1Y":
        start_d = today - timedelta(days=365)
        end_d = today
    elif range_option == "5Y":
        start_d = today - timedelta(days=1825)
        end_d = today
    else:  # Custom
        c_custom_start, c_custom_end = st.columns(2)
        with c_custom_start:
            start_d = st.date_input("Start Date", value=today - timedelta(days=30))  # type: ignore[assignment]
        with c_custom_end:
            end_d = st.date_input("End Date", value=today)  # type: ignore[assignment]

    if st.button("Load Historical Trends", type="primary", use_container_width=True):
        with st.spinner(
            f"Fetching historical {hist_base}/{hist_target} series from backend..."
        ):
            ts_res = client.get_timeseries(
                start_date=start_d.isoformat(),
                end_date=end_d.isoformat(),
                base=hist_base,
                symbols=[hist_target],
            )

        if ts_res.get("success"):
            ts_data = ts_res.get("data", {})
            ts_meta = ts_res.get("meta", {})
            rates_map = ts_data.get("rates", {})
            stats_map = ts_data.get("statistics", {})
            target_stats = stats_map.get(hist_target, {})

            if not rates_map:
                st.warning(
                    f"No published rates found for {hist_base}/{hist_target} in the selected range."
                )
            else:
                st.markdown("---")
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Start Rate", target_stats.get("start_rate", "N/A"))
                m2.metric("End Rate", target_stats.get("end_rate", "N/A"))
                m3.metric(
                    "Min Rate",
                    target_stats.get("min_rate", "N/A"),
                    help=f"Date: {target_stats.get('min_date', '')}",
                )
                m4.metric(
                    "Max Rate",
                    target_stats.get("max_rate", "N/A"),
                    help=f"Date: {target_stats.get('max_date', '')}",
                )

                chg_str = target_stats.get("change_pct", "0.0000")
                try:
                    chg_val = float(chg_str)
                    chg_display = f"{'+' if chg_val > 0 else ''}{chg_str}%"
                except ValueError:
                    chg_display = f"{chg_str}%"
                m5.metric("% Change", chg_display, delta=f"{chg_str}%")

                chart_records: list[dict[str, Any]] = []
                for d_str in sorted(rates_map.keys()):
                    day_rates = rates_map[d_str]
                    if hist_target in day_rates:
                        try:
                            rate_flt = float(day_rates[hist_target])
                            chart_records.append(
                                {
                                    "Date": d_str,
                                    "Rate": rate_flt,
                                    "Rate_Decimal": day_rates[hist_target],
                                }
                            )
                        except (ValueError, TypeError):
                            continue

                if chart_records:
                    df = pd.DataFrame(chart_records)
                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=df["Date"],
                            y=df["Rate"],
                            mode="lines+markers",
                            name=f"{hist_base}/{hist_target}",
                            line={"color": "#1E88E5", "width": 2.5},
                            marker={"size": 4},
                            hovertemplate=(
                                "<b>Date:</b> %{x}<br>"
                                f"<b>Rate ({hist_target} per 1 {hist_base}):</b> "
                                "%{text}<extra></extra>"
                            ),
                            text=df["Rate_Decimal"],
                        )
                    )
                    fig.update_layout(
                        title=f"{hist_base} to {hist_target} Historical Exchange Rate",
                        xaxis_title="Date",
                        yaxis_title=f"Rate ({hist_target})",
                        template="plotly_white",
                        hovermode="x unified",
                        height=420,
                        margin={"l": 20, "r": 20, "t": 50, "b": 30},
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    with st.expander("📋 View Daily Rates Table"):
                        st.dataframe(
                            df[["Date", "Rate_Decimal"]].rename(
                                columns={"Rate_Decimal": f"Rate ({hist_target})"}
                            ),
                            use_container_width=True,
                        )

                st.caption(
                    f"Source: {ts_meta.get('provider', '').capitalize()} | "
                    f"Dates covered: {ts_data.get('count_dates', 0)} published reference points."
                )
        else:
            err = ts_res.get("error", {})
            st.error(
                f"**[{err.get('code', 'ERROR')}]:** "
                f"{err.get('message', 'Failed to retrieve historical timeseries.')}"
            )

# -----------------------------------------------------------------------------
# TAB 5: CONVERSION HISTORY & CSV EXPORT
# -----------------------------------------------------------------------------
with tab_history:
    st.markdown("##### Conversion History for Active Session")

    hist_action_col1, hist_action_col2 = st.columns([1, 4])
    with hist_action_col1:
        if st.button("🗑️ Clear History", help="Delete all history for this session"):
            client.clear_history(st.session_state["session_id"])
            st.success("History cleared.")
            st.rerun()

    with hist_action_col2:
        export_url = client.export_history_csv_url(st.session_state["session_id"])
        st.markdown(f"[📥 Download CSV Export]({export_url})")

    # Query history
    history_res = client.get_history(st.session_state["session_id"], limit=100)
    if history_res.get("success") and history_res.get("data"):
        h_data = history_res["data"]
        items = h_data.get("items", [])
        total_items = h_data.get("total", 0)

        if not items:
            st.info(
                "No conversion history recorded yet. Perform conversions in Tab 1 to see them logged here."
            )
        else:
            st.caption(f"Showing {len(items)} of {total_items} logged conversions.")
            h_rows = [
                {
                    "ID": it["id"],
                    "Timestamp (UTC)": it["created_at"][:19].replace("T", " "),
                    "From": f"{CURRENCY_FLAGS.get(it['from'], '🌐')} {it['from']}",
                    "Amount": format_money_str(it["amount"]),
                    "To": f"{CURRENCY_FLAGS.get(it['to'], '🌐')} {it['to']}",
                    "Converted Amount": format_money_str(it["converted_amount"]),
                    "Applied Rate": it["rate"],
                }
                for it in items
            ]
            st.dataframe(
                pd.DataFrame(h_rows), use_container_width=True, hide_index=True
            )
    else:
        st.warning("Could not load conversion history from backend.")

# -----------------------------------------------------------------------------
# TAB 6: CURRENCY EXPLORER
# -----------------------------------------------------------------------------
with tab_explorer:
    st.markdown("##### Supported Currencies Catalog & Minor Unit Standards")

    search_query = (
        st.text_input("🔍 Search currency code or name", value="").strip().upper()
    )

    # Base currency to show indicative reference rate against
    exp_base = st.selectbox(
        "Show Indicative Rate Against",
        options=currency_codes,
        index=currency_codes.index("USD") if "USD" in currency_codes else 0,
        key="exp_base_select",
    )

    exp_rates_res = client.get_rates(base=exp_base)
    exp_rates = (
        exp_rates_res.get("data", {}).get("rates", {})
        if exp_rates_res.get("success")
        else {}
    )

    explorer_rows = []
    for c in currency_items:
        code = c["code"]
        name = c["name"]
        if search_query and (
            search_query not in code and search_query.lower() not in name.lower()
        ):
            continue

        rate_str = exp_rates.get(code, "1.0" if code == exp_base else "N/A")

        explorer_rows.append(
            {
                "Flag": CURRENCY_FLAGS.get(code, "🌐"),
                "Code (ISO 4217)": code,
                "Currency Name": name,
                "Symbol": CURRENCY_SYMBOLS.get(code, "-"),
                "Minor Units (Decimals)": c.get("minor_units", 2),
                f"Rate (per 1 {exp_base})": rate_str,
            }
        )

    st.dataframe(pd.DataFrame(explorer_rows), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# TAB 7: SETTINGS & PREFERENCES
# -----------------------------------------------------------------------------
with tab_settings:
    st.markdown("##### User Preferences & Session Configuration")

    set_col1, set_col2 = st.columns(2)
    with set_col1:
        new_default_base = st.selectbox(
            "Default Base Currency",
            options=currency_codes,
            index=currency_codes.index(st.session_state["default_base"])
            if st.session_state["default_base"] in currency_codes
            else 0,
        )
        st.session_state["default_base"] = new_default_base

        new_fmt = st.selectbox(
            "Number Formatting Convention",
            options=["US (1,234.56)", "EU (1.234,56)"],
            index=0 if st.session_state["number_format"] == "US (1,234.56)" else 1,
        )
        st.session_state["number_format"] = new_fmt

    with set_col2:
        new_rounding = st.selectbox(
            "Rounding Policy",
            options=[
                "ROUND_HALF_UP (Standard Commercial)",
                "ROUND_HALF_EVEN (Banker's)",
            ],
            index=0 if st.session_state["rounding_policy"] == "ROUND_HALF_UP" else 1,
        )
        st.session_state["rounding_policy"] = (
            "ROUND_HALF_UP" if "HALF_UP" in new_rounding else "ROUND_HALF_EVEN"
        )

        st.markdown(
            f"**Current Anonymous Session ID:** `{st.session_state['session_id']}`"
        )
        if st.button("🔄 Generate New Session ID"):
            st.session_state["session_id"] = uuid.uuid4().hex[:16]
            st.success("New session ID generated!")
            st.rerun()

    st.markdown("---")
    st.info(
        "💡 Settings are preserved across actions in this session. "
        "Conversions, favorites, and history are keyed to your anonymous Session ID."
    )
