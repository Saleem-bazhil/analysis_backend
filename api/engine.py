"""
Call Plan Comparison Engine.

Ports the JavaScript comparison engine logic to Python.
Processes HP Flex WIP Excel/CSV reports and generates classified call plans.
"""

import re
from datetime import datetime
from dateutil import parser as dateutil_parser
import pandas as pd


# ---------------------------------------------------------------------------
# Column name fuzzy matching maps
# ---------------------------------------------------------------------------

FLEX_COLUMN_MAP = {
    'ticket_no': ['Ticket No', 'TicketNo', 'WorkOrder', 'Ticket_No', 'ticket no', 'ticketno', 'workorder'],
    'case_id': ['Case Id', 'CaseId', 'Case_Id', 'case id', 'caseid'],
    'product': ['Product Name', 'ProductName', 'Product_Name', 'product name', 'productname'],
    'asp_city': ['ASP City', 'ASPCity', 'ASP_City', 'asp city', 'aspcity'],
    'wo_otc_code': ['WO OTC Code', 'Wo otc code', 'WO_OTC_Code', 'wo otc code', 'WoOtcCode'],
    'flex_status': ['Status', 'Flex Status', 'FlexStatus', 'Flex_Status', 'status', 'flex status'],
    'contact_no': ['Customer Phone No', 'Phone', 'CustomerPhoneNo', 'Customer_Phone_No', 'customer phone no', 'phone'],
    'hp_owner': ['HP Owner', 'HPOwner', 'HP_Owner', 'hp owner', 'hpowner'],
    'create_time': ['Create Time', 'CreateTime', 'Create_Time', 'create time', 'createtime'],
    'business_segment': ['Business Segment', 'BusinessSegment', 'Business_Segment', 'business segment', 'businesssegment'],
    'wip_aging': ['WIP Aging', 'WIPAging', 'WIP_Aging', 'wip aging', 'wipage', 'wiping'],
    'work_location': ['Work Location', 'WorkLocation', 'Work_Location', 'work location', 'worklocation'],
}

CALLPLAN_COLUMN_MAP = {
    'month': ['Month', 'month'],
    'ticket_no': ['Ticket No', 'TicketNo', 'Ticket_No', 'ticket no'],
    'case_id': ['Case Id', 'CaseId', 'Case_Id', 'case id'],
    'wo_otc_code': ['WO OTC Code', 'Wo otc code', 'WO_OTC_Code', 'wo otc code'],
    'product': ['Product', 'product', 'Product Name'],
    'wip_aging': ['WIP Aging', 'WIPAging', 'WIP_Aging', 'wip aging'],
    'location': ['Location', 'location', 'Work Location'],
    'segment': ['Segment', 'segment'],
    'hp_owner': ['HP Owner', 'HPOwner', 'hp owner'],
    'flex_status': ['Flex Status', 'FlexStatus', 'flex status', 'Status'],
    'morning_status': ['Morning Report', 'Morning_Report', 'morning report'],
    'evening_status': ['Evening Report', 'Evening_Report', 'evening report'],
    'current_status_tat': ['Current Status-TAT', 'Current_Status_TAT', 'current status-tat'],
    'engineer': ['Engg.', 'Engg', 'Engineer', 'engg.', 'engg'],
    'contact_no': ['Contact no.', 'Contact No', 'ContactNo', 'contact no.', 'contact no'],
    'parts': ['Parts', 'parts'],
    'wip_changed': ['WIP Changed', 'WIPChanged', 'wip changed'],
}


def clean_phone(raw):
    """
    Clean a phone number string.

    "916381510725" -> "6381510725", remove trailing ".0", strip "91" prefix if 12 digits.
    """
    s = str(raw if raw is not None else '').strip()
    # Remove trailing .0 (common in Excel numeric-to-string conversion)
    s = re.sub(r'\.0$', '', s)
    # Remove all non-digit characters
    s = re.sub(r'\D', '', s)
    # Strip 91 country code prefix if 12 digits
    if len(s) == 12 and s.startswith('91'):
        s = s[2:]
    # If still longer than 10, take last 10
    if len(s) > 10:
        s = s[-10:]
    return s


def map_segment(otc_code, business_segment):
    """
    Map segment from OTC code and business segment.

    OTC contains "trade" -> "Trade"
    OTC contains "install" or "05f" -> "Install"
    Business Segment "Computing" -> "Pc"
    Business Segment "Printing" -> "print"
    default: Business Segment as-is or "Trade"
    """
    otc = str(otc_code or '').lower()
    bseg = str(business_segment or '').strip()

    if 'trade' in otc:
        return 'Trade'
    if 'install' in otc or '05f' in otc:
        return 'Install'
    if bseg.lower() == 'computing':
        return 'Pc'
    if bseg.lower() == 'printing':
        return 'print'
    if bseg:
        return bseg
    return 'Trade'


def parse_flex_date(raw):
    """
    Parse Flex date format: "Wed Mar 11 16:13:41 UTC 2026" -> datetime.

    Strips " UTC" before parsing.
    """
    s = str(raw or '').strip()
    if not s:
        return None
    # Remove UTC timezone marker for simpler parsing
    s = s.replace(' UTC', '')
    try:
        return dateutil_parser.parse(s)
    except (ValueError, TypeError):
        return None


def resolve_columns(df, column_map):
    """
    Resolve actual DataFrame column names using the fuzzy mapping.

    Returns a dict: {standard_key: actual_column_name_in_df}.
    """
    resolved = {}
    df_cols = list(df.columns)
    # Build a lowercase lookup
    df_cols_lower = [c.strip().lower() for c in df_cols]

    for key, candidates in column_map.items():
        found = None
        for candidate in candidates:
            candidate_lower = candidate.strip().lower()
            if candidate_lower in df_cols_lower:
                idx = df_cols_lower.index(candidate_lower)
                found = df_cols[idx]
                break
        resolved[key] = found
    return resolved


def safe_str(val):
    """Convert a value to string safely, handling NaN/None."""
    if val is None:
        return ''
    if isinstance(val, float) and pd.isna(val):
        return ''
    return str(val).strip()


def safe_int(val, default=0):
    """Convert a value to int safely."""
    if val is None:
        return default
    if isinstance(val, float) and pd.isna(val):
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def read_file_to_df(file_path):
    """
    Read an Excel or CSV file into a DataFrame.

    Supports .xlsx, .xls, and .csv files.
    """
    path_str = str(file_path).lower()
    if path_str.endswith('.csv'):
        df = pd.read_csv(file_path, dtype=str)
    else:
        df = pd.read_excel(file_path, dtype=str, engine='openpyxl')
    # Strip whitespace from column names
    df.columns = [c.strip() for c in df.columns]
    return df


def extract_flex_row(row, col_map):
    """Extract a normalized dict from a flex WIP row using the resolved column map."""
    def g(key):
        col = col_map.get(key)
        if col is None:
            return ''
        return safe_str(row.get(col, ''))

    return {
        'ticket_no': g('ticket_no'),
        'case_id': g('case_id'),
        'product': g('product'),
        'wo_otc_code': g('wo_otc_code'),
        'flex_status': g('flex_status'),
        'contact_no': clean_phone(g('contact_no')),
        'hp_owner': g('hp_owner'),
        'create_time': g('create_time'),
        'business_segment': g('business_segment'),
        'wip_aging': safe_int(g('wip_aging')),
        'work_location': g('work_location'),
        'asp_city': g('asp_city'),
    }


def extract_callplan_row(row, col_map):
    """Extract a normalized dict from a yesterday call plan row."""
    def g(key):
        col = col_map.get(key)
        if col is None:
            return ''
        return safe_str(row.get(col, ''))

    return {
        'month': g('month'),
        'ticket_no': g('ticket_no'),
        'case_id': g('case_id'),
        'wo_otc_code': g('wo_otc_code'),
        'product': g('product'),
        'wip_aging': safe_int(g('wip_aging')),
        'location': g('location'),
        'segment': g('segment'),
        'hp_owner': g('hp_owner'),
        'flex_status': g('flex_status'),
        'morning_status': g('morning_status'),
        'evening_status': g('evening_status'),
        'current_status_tat': g('current_status_tat'),
        'engineer': g('engineer'),
        'contact_no': g('contact_no'),
        'parts': g('parts'),
        'wip_changed': g('wip_changed'),
    }


def process_call_plan(flex_file_path, callplan_file_path, city='Chennai', report_date=None):
    """
    Main comparison engine.

    1. Filter flex by city, deduplicate by ticket_no (last wins).
    2. Load yesterday's call plan.
    3. Classify:
       - PENDING = in both flex and yesterday (carry yesterday's data, aging from flex or +1)
       - NEW = in flex but not yesterday (populate from flex, map segment, clean phone)
       - DROPPED = in yesterday but not flex (excluded from output)
    4. Sort: PENDING by aging desc, then NEW by aging desc.

    Returns:
        dict with keys: pending, new, dropped, all_rows, summary
    """
    # Read files
    flex_df = read_file_to_df(flex_file_path)
    flex_col_map = resolve_columns(flex_df, FLEX_COLUMN_MAP)

    # Filter by city
    city_col = flex_col_map.get('asp_city')
    if city_col and city:
        city_lower = city.lower()
        flex_df = flex_df[
            flex_df[city_col].fillna('').str.strip().str.lower() == city_lower
        ].copy()

    # Extract and deduplicate flex rows (last wins)
    flex_map = {}
    for _, row in flex_df.iterrows():
        fr = extract_flex_row(row, flex_col_map)
        ticket = fr['ticket_no']
        if ticket:
            flex_map[ticket] = fr

    # Read yesterday's call plan (may be None)
    yesterday_map = {}
    if callplan_file_path:
        cp_df = read_file_to_df(callplan_file_path)
        cp_col_map = resolve_columns(cp_df, CALLPLAN_COLUMN_MAP)
        for _, row in cp_df.iterrows():
            cr = extract_callplan_row(row, cp_col_map)
            ticket = cr['ticket_no']
            if ticket:
                yesterday_map[ticket] = cr

    flex_tickets = set(flex_map.keys())
    yesterday_tickets = set(yesterday_map.keys())

    # Classify
    pending_tickets = flex_tickets & yesterday_tickets
    new_tickets = flex_tickets - yesterday_tickets
    dropped_tickets = yesterday_tickets - flex_tickets

    # Determine report month
    if report_date:
        if isinstance(report_date, str):
            report_date = dateutil_parser.parse(report_date).date()
        month_str = report_date.strftime('%B')
    else:
        month_str = datetime.now().strftime('%B')

    # Build PENDING rows: carry yesterday's data, update aging from flex
    pending_rows = []
    for ticket in pending_tickets:
        yest = yesterday_map[ticket]
        flex = flex_map[ticket]
        flex_aging = flex.get('wip_aging', 0)
        yest_aging = yest.get('wip_aging', 0)
        aging = flex_aging if flex_aging > 0 else (yest_aging + 1)

        pending_rows.append({
            'ticket_no': ticket,
            'case_id': yest.get('case_id', '') or flex.get('case_id', ''),
            'product': yest.get('product', '') or flex.get('product', ''),
            'wip_aging': aging,
            'location': yest.get('location', '') or flex.get('work_location', ''),
            'segment': yest.get('segment', ''),
            'classification': 'PENDING',
            'morning_status': yest.get('morning_status', ''),
            'evening_status': yest.get('evening_status', ''),
            'engineer': yest.get('engineer', ''),
            'contact_no': yest.get('contact_no', ''),
            'parts': yest.get('parts', ''),
            'month': yest.get('month', '') or month_str,
            'wo_otc_code': yest.get('wo_otc_code', '') or flex.get('wo_otc_code', ''),
            'hp_owner': yest.get('hp_owner', '') or flex.get('hp_owner', ''),
            'flex_status': flex.get('flex_status', '') or yest.get('flex_status', ''),
            'wip_changed': '',
            'current_status_tat': yest.get('current_status_tat', ''),
        })

    # Build NEW rows: populate from flex
    new_rows = []
    for ticket in new_tickets:
        flex = flex_map[ticket]
        segment = map_segment(flex.get('wo_otc_code', ''), flex.get('business_segment', ''))

        new_rows.append({
            'ticket_no': ticket,
            'case_id': flex.get('case_id', ''),
            'product': flex.get('product', ''),
            'wip_aging': flex.get('wip_aging', 0),
            'location': flex.get('work_location', ''),
            'segment': segment,
            'classification': 'NEW',
            'morning_status': 'To be scheduled',
            'evening_status': '',
            'engineer': '',
            'contact_no': flex.get('contact_no', ''),
            'parts': '',
            'month': month_str,
            'wo_otc_code': flex.get('wo_otc_code', ''),
            'hp_owner': flex.get('hp_owner', ''),
            'flex_status': flex.get('flex_status', ''),
            'wip_changed': '',
            'current_status_tat': '',
        })

    # Build DROPPED rows (for reference, excluded from output)
    dropped_rows = []
    for ticket in dropped_tickets:
        yest = yesterday_map[ticket]
        dropped_rows.append({
            'ticket_no': ticket,
            'case_id': yest.get('case_id', ''),
            'product': yest.get('product', ''),
            'wip_aging': yest.get('wip_aging', 0),
            'location': yest.get('location', ''),
            'segment': yest.get('segment', ''),
            'classification': 'DROPPED',
            'morning_status': yest.get('morning_status', ''),
            'evening_status': yest.get('evening_status', ''),
            'engineer': yest.get('engineer', ''),
            'contact_no': yest.get('contact_no', ''),
            'parts': yest.get('parts', ''),
            'month': yest.get('month', ''),
            'wo_otc_code': yest.get('wo_otc_code', ''),
            'hp_owner': yest.get('hp_owner', ''),
            'flex_status': yest.get('flex_status', ''),
            'wip_changed': '',
            'current_status_tat': yest.get('current_status_tat', ''),
        })

    # Sort: PENDING by aging desc, then NEW by aging desc
    pending_rows.sort(key=lambda r: r['wip_aging'], reverse=True)
    new_rows.sort(key=lambda r: r['wip_aging'], reverse=True)

    all_rows = pending_rows + new_rows

    summary = {
        'total': len(all_rows),
        'pending': len(pending_rows),
        'new': len(new_rows),
        'dropped': len(dropped_rows),
        'city': city,
        'report_date': str(report_date) if report_date else None,
    }

    return {
        'pending': pending_rows,
        'new': new_rows,
        'dropped': dropped_rows,
        'all_rows': all_rows,
        'summary': summary,
    }


def generate_export_df(rows):
    """
    Convert processed rows into a DataFrame ready for Excel export.

    Column order matches the expected call plan output format.
    """
    columns = [
        'Month', 'Ticket No', 'Case Id', 'WO OTC Code', 'Product',
        'WIP Aging', 'Location', 'Segment', 'HP Owner', 'Flex Status',
        'Morning Report', 'Evening Report', 'Current Status-TAT',
        'Engg.', 'Contact no.', 'Parts', 'WIP Changed', 'Classification',
    ]

    data = []
    for r in rows:
        data.append({
            'Month': r.get('month', ''),
            'Ticket No': r.get('ticket_no', ''),
            'Case Id': r.get('case_id', ''),
            'WO OTC Code': r.get('wo_otc_code', ''),
            'Product': r.get('product', ''),
            'WIP Aging': r.get('wip_aging', 0),
            'Location': r.get('location', ''),
            'Segment': r.get('segment', ''),
            'HP Owner': r.get('hp_owner', ''),
            'Flex Status': r.get('flex_status', ''),
            'Morning Report': r.get('morning_status', ''),
            'Evening Report': r.get('evening_status', ''),
            'Current Status-TAT': r.get('current_status_tat', ''),
            'Engg.': r.get('engineer', ''),
            'Contact no.': r.get('contact_no', ''),
            'Parts': r.get('parts', ''),
            'WIP Changed': r.get('wip_changed', ''),
            'Classification': r.get('classification', ''),
        })

    return pd.DataFrame(data, columns=columns)
