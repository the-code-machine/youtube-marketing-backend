from sqlalchemy.orm import Session
from datetime import datetime
from app.models.email_template import EmailTemplate
from app.schemas.template import TemplateCreate, TemplateUpdate

class TemplateService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_templates(self):
        """Fetch all templates ordered by newest first."""
        return self.db.query(EmailTemplate).order_by(EmailTemplate.created_at.desc()).all()

    def get_template(self, template_id: int):
        return self.db.query(EmailTemplate).get(template_id)

    def create_template(self, data: TemplateCreate):
        new_template = EmailTemplate(
            title=data.title,
            subject=data.subject,
            body=data.body,
            ai_prompt_instructions=data.ai_prompt_instructions,
            category=data.category,
            is_active=data.is_active,
            created_at=datetime.utcnow(),
            user_id=1 # Default user or fetch from context
        )
        self.db.add(new_template)
        self.db.commit()
        self.db.refresh(new_template)
        return new_template

    def update_template(self, template_id: int, data: TemplateUpdate):
        template = self.get_template(template_id)
        if not template:
            return None
        
        # Update only provided fields
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(template, key, value)
            
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, template_id: int):
        template = self.get_template(template_id)
        if not template:
            return False
            
        self.db.delete(template)
        self.db.commit()
        return True