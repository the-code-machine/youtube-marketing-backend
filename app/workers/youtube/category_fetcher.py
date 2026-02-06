from app.models.target_category import TargetCategory

def get_active_categories(db):
    return db.query(TargetCategory)\
        .filter(TargetCategory.is_active == True)\
        .order_by(TargetCategory.priority.desc())\
        .all()
