# Organization code structure

## Department folders
Mỗi phòng ban có folder riêng trong `departments/` gồm:
- `employees.py`: nhân sự thực thi
- `leader.py`: leader chịu trách nhiệm phê duyệt
- `policy.py`: policy nội bộ của phòng ban

Danh sách phòng ban:
- account
- strategy
- creative
- media
- tech
- data
- production
- sales
- operations
- finance

## Inter-department policies
- File `src/policies/interdepartment_policies.py` chứa policy handoff giữa các phòng ban.
- Mỗi policy có: from_department, to_department, required_inputs, expected_outputs, SLA, approver_role.

## Runtime validation
Chạy:
```bash
PYTHONPATH=. python src/main.py
```
