import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
import tempfile
import io

st.set_page_config(
    page_title="IFRS 16 Lease Calculator",
    page_icon="📊",
    layout="centered"
)

st.title("IFRS 16 Lease Schedule Calculator")
st.markdown("Calculate lease liability, ROU asset depreciation, and generate journal entries under IFRS 16.")

# INPUTS
col1, col2 = st.columns(2)

with col1:
    lease_term_years = st.number_input("Lease Term (years)", min_value=1, max_value=50, value=5, step=1)
    payments_per_year = st.selectbox("Payments per Year", options=[1, 2, 4, 12], index=3)  # default monthly
    lease_payment = st.number_input("Lease Payment per Period", min_value=0.0, value=10000.0, step=100.0)

with col2:
    discount_rate_annual = st.number_input("Annual Discount Rate (%)", min_value=0.0, value=5.0, step=0.1) / 100
    start_date = st.date_input("Lease Commencement Date", value=datetime.today().date())
    payment_timing = st.selectbox(
        "Payment Timing",
        options=["End of Period (Ordinary Annuity)", "Beginning of Period (Annuity Due)"],
        help="Most leases are paid in advance (Annuity Due)"
    )

if st.button("Generate IFRS 16 Schedules", type="primary", use_container_width=True):
    periods = int(lease_term_years * payments_per_year)
    rate_per_period = discount_rate_annual / payments_per_year

    # PV of lease payments
    if payment_timing == "End of Period (Ordinary Annuity)":
        # annuity formula for payments at end of period
        if rate_per_period == 0:
            pv = lease_payment * periods
        else:
            pv = lease_payment * (1 - (1 + rate_per_period) ** -periods) / rate_per_period
    else:
        # Annuity Due: payments at beginning of period
        if rate_per_period == 0:
            pv = lease_payment * periods
        else:
            pv = lease_payment * (1 - (1 + rate_per_period) ** -periods) / rate_per_period * (1 + rate_per_period)

    # Lease Liability Amortization Schedule
    liability_schedule = []
    opening_balance = pv
    current_date = datetime.combine(start_date, datetime.min.time())
    months_per_period = 12 // payments_per_year

    for period in range(1, periods + 1):
        if payment_timing == "Beginning of Period (Annuity Due)" and period == 1:
            interest = 0.0
        else:
            interest = opening_balance * rate_per_period

        principal_reduction = lease_payment - interest
        closing_balance = opening_balance - principal_reduction

        liability_schedule.append({
            "Period": period,
            "Date": current_date.strftime("%Y-%m-%d"),
            "Opening Balance": round(opening_balance, 2),
            "Interest Expense": round(interest, 2),
            "Lease Payment": round(lease_payment, 2),
            "Principal Reduction": round(principal_reduction, 2),
            "Closing Balance": round(max(closing_balance, 0), 2)  
        })

        opening_balance = closing_balance
        current_date += relativedelta(months=months_per_period)

    liability_df = pd.DataFrame(liability_schedule)

    # Right-of-Use (ROU) Asset Depreciation
    depreciation_per_period = pv / periods
    rou_schedule = []
    carrying_amount = pv
    current_date = datetime.combine(start_date, datetime.min.time())

    for period in range(1, periods + 1):
        closing_amount = carrying_amount - depreciation_per_period

        rou_schedule.append({
            "Period": period,
            "Date": current_date.strftime("%Y-%m-%d"),
            "Opening ROU": round(carrying_amount, 2),
            "Depreciation": round(depreciation_per_period, 2),
            "Closing ROU": round(max(closing_amount, 0), 2)
        })

        carrying_amount = closing_amount
        current_date += relativedelta(months=months_per_period)

    rou_df = pd.DataFrame(rou_schedule)

    # JEs
    journals = []

    # Initial recognition
    journals.append({
        "Date": start_date.strftime("%Y-%m-%d"),
        "Description": "Initial recognition of lease",
        "Debit": f"Right-of-use asset {round(pv, 2):,}",
        "Credit": f"Lease liability {round(pv, 2):,}"
    })

    # Periodic entries
    for liab, rou in zip(liability_schedule, rou_schedule):
        # Lease payment + interest
        journals.append({
            "Date": liab["Date"],
            "Description": f"Lease payment - Period {liab['Period']}",
            "Debit": f"Interest expense {liab['Interest Expense']:,} | Lease liability {liab['Principal Reduction']:,}",
            "Credit": f"Cash/Bank {liab['Lease Payment']:,}"
        })

        # Depreciation
        journals.append({
            "Date": rou["Date"],
            "Description": f"Depreciation of ROU asset - Period {rou['Period']}",
            "Debit": f"Depreciation expense {rou['Depreciation']:,}",
            "Credit": f"Accumulated depreciation - ROU {rou['Depreciation']:,}"
        })

    journal_df = pd.DataFrame(journals)

    # Results
    st.success(f"Initial Lease Liability (Present Value): **{round(pv, 2):,}**")

    st.subheader("Lease Liability Schedule")
    st.dataframe(liability_df, use_container_width=True, hide_index=True)

    st.subheader("Right-of-Use Asset Schedule")
    st.dataframe(rou_df, use_container_width=True, hide_index=True)

    st.subheader("Journal Entries")
    st.dataframe(journal_df, use_container_width=True, hide_index=True)

    # DOWNLOADS
    st.divider()
    col_a, col_b, col_c, col_d = st.columns(4)

    with col_a:
        st.download_button(
            "📥 Liability CSV",
            liability_df.to_csv(index=False),
            file_name="lease_liability_schedule.csv",
            mime="text/csv"
        )

    with col_b:
        st.download_button(
            "📥 ROU CSV",
            rou_df.to_csv(index=False),
            file_name="rou_asset_schedule.csv",
            mime="text/csv"
        )

    with col_c:
        st.download_button(
            "📥 Journal Entries CSV",
            journal_df.to_csv(index=False),
            file_name="ifrs16_journal_entries.csv",
            mime="text/csv"
        )

    # PDF report
    def create_pdf():
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("IFRS 16 Lease Report", styles['Title']))
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(f"Lease Commencement: {start_date}", styles['Normal']))
        elements.append(Paragraph(f"Initial Lease Liability: {round(pv, 2):,}", styles['Normal']))
        elements.append(Spacer(1, 20))

        def add_table(df, title):
            elements.append(Paragraph(title, styles['Heading2']))
            data = [df.columns.tolist()] + df.values.tolist()
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))

        add_table(liability_df.head(12), "Lease Liability Schedule (First 12 periods)")
        add_table(rou_df.head(12), "ROU Asset Depreciation Schedule (First 12 periods)")

        doc.build(elements)
        buffer.seek(0)
        return buffer

    pdf_buffer = create_pdf()

    with col_d:
        st.download_button(
            "📄 Download PDF Report",
            data=pdf_buffer,
            file_name=f"IFRS16_Lease_Report_{start_date}.pdf",
            mime="application/pdf"
        )

st.caption("Built for practical IFRS 16 compliance • Straight-line ROU depreciation • Supports payments in advance or arrears")
