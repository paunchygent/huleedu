# ADR-002: Student Record to User Account Linking Strategy

## Status
Proposed

## Context
Currently, students exist only as data records created by teachers in the Class Management Service. Future requirements include:

1. Students need to log in to view their essays and feedback
2. Student records (in class_management_service) need to link to user accounts (in future user_management_service)
3. Must maintain data integrity and teacher ownership of student records

## Decision
Use a **separate linking table** to connect student records to user accounts:

```sql
-- In future user_management_service
CREATE TABLE user_student_links (
    user_id UUID REFERENCES users(id),
    student_record_id UUID REFERENCES class_management.students(id),
    linked_at TIMESTAMP DEFAULT NOW(),
    linked_by_user_id VARCHAR(255), -- teacher who approved
    PRIMARY KEY (user_id, student_record_id)
);
```

## Consequences

### Positive
- No schema changes to existing Class Management Service
- Maintains service boundaries and independence
- Supports complex scenarios (transferred students, multiple enrollments)
- Audit trail of who linked accounts and when
- Flexible for future requirements

### Negative
- Additional join required for queries
- More complex than direct foreign key
- Need to build invitation/linking flow

## Alternatives Considered

1. **Add user_id to students table**: Rejected as it violates service boundaries
2. **Duplicate student data in user service**: Rejected due to data consistency issues
3. **Merge services**: Rejected as it breaks bounded contexts

## Implementation Notes
1. Teacher creates student record (existing flow)
2. System generates invitation code
3. Student creates user account with invitation
4. System creates link in user_student_links table
5. Student can access their essays via user account

## References
- Future User Management Service design
- Class Management Service current implementation
