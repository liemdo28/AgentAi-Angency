from models import Employee

EMPLOYEES = [
    Employee(
        id="data_emp_analyst_01",
        full_name="Data Analyst 01",
        role="Data Analyst",
        department="data",
        responsibilities=(
            "Phân tích CPA/ROAS/LTV theo campaign.",
            "Phát hiện anomaly và đề xuất action.",
            "Chuẩn hóa báo cáo tuần/tháng cho Account.",
        ),
    ),
    Employee(
        id="data_emp_engineer_01",
        full_name="Data Engineer 01",
        role="Data Engineer",
        department="data",
        responsibilities=(
            "Xây và vận hành data pipeline.",
            "Đảm bảo ETL job chạy đúng SLA.",
            "Quản lý schema evolution và data quality checks.",
        ),
    ),
    Employee(
        id="data_emp_bi_01",
        full_name="BI Developer 01",
        role="BI Developer",
        department="data",
        responsibilities=(
            "Xây dashboard cho đa phòng ban.",
            "Tối ưu query và semantic layer.",
            "Huấn luyện team đọc dashboard đúng chuẩn metric.",
        ),
    ),
]
