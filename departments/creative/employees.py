from models import Employee

EMPLOYEES = [
    Employee(
        id="creative_emp_design_01",
        full_name="Graphic Designer 01",
        role="Graphic Designer",
        department="creative",
        responsibilities=(
            "Thiết kế key visual và banner ads.",
            "Xuất asset theo channel spec.",
            "Phối hợp Production cho post-production.",
        ),
    ),
    Employee(
        id="creative_emp_copy_01",
        full_name="Copywriter 01",
        role="Copywriter",
        department="creative",
        responsibilities=(
            "Viết headline/body copy theo funnel.",
            "Tạo biến thể copy cho A/B testing.",
            "Đồng bộ tone-of-voice với brand guideline.",
        ),
    ),
    Employee(
        id="creative_emp_video_01",
        full_name="Video Editor 01",
        role="Video Editor",
        department="creative",
        responsibilities=(
            "Dựng video ads short-form.",
            "Tối ưu opening hook theo retention data.",
            "Bàn giao file master đúng chuẩn media team.",
        ),
    ),
]
