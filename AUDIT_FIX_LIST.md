# Audit Fix List (Implemented)

## 1) Đưa CRM/Automation vào code structure
- [x] Thêm folder `departments/crm_automation/` gồm `employees.py`, `leader.py`, `policy.py`.
- [x] Thêm `crm_automation` vào `DEPARTMENT_KEYS` để runtime load chính thức.
- [x] Thêm policy liên thông: `data -> crm_automation`, `crm_automation -> media`, `crm_automation -> account`.

## 2) Xóa duplicate model source
- [x] Xóa `src/models.py`.
- [x] Giữ một nguồn model duy nhất tại `models.py`.

## 3) Policy phòng ban không còn generic
- [x] Viết lại `departments/*/policy.py` cho từng phòng ban với output/input chuyên biệt.

## 4) Mở rộng validator
- [x] Check duplicate route policy.
- [x] Check approver role khớp với leader role của phòng ban đích.
- [x] Check empty input/output.
- [x] Check missing critical routes.
- [x] Check orphan department (thiếu inbound hoặc outbound route).
- [x] Check bundle sanity (có employees, policy đủ input/output).

## 5) Tách role trong Creative và Data
- [x] Creative: Graphic Designer, Copywriter, Video Editor.
- [x] Data: Data Analyst, Data Engineer, BI Developer.

## 6) Bổ sung flow còn thiếu
- [x] `media -> account`
- [x] `creative -> production`
- [x] `account -> finance`
- [x] `data -> strategy`
- [x] `tech -> operations`
