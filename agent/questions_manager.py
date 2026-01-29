"""
Questions Manager for Curiosity Agent.
Handles non-blocking user questions with async answers.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
import uuid


@dataclass
class Question:
    """A question for the user."""
    id: str
    question_text: str
    question_type: str  # multiple_choice, free_text, yes_no, rating
    options: list[str]  # For multiple_choice
    priority: str  # low, medium, high
    context: str  # Why the agent is asking
    created_at: str
    status: str  # pending, answered
    answer: Optional[str] = None
    answer_text: Optional[str] = None  # For "other" option
    answered_at: Optional[str] = None


class QuestionsManager:
    """
    Manages the questions panel for async user interaction.
    
    The agent posts questions and continues working.
    Users can answer whenever they want.
    Agent is notified of new answers at each loop iteration.
    """
    
    def __init__(self, questions_path: str = "questions/pending.json"):
        self.questions_path = Path(questions_path)
        self.questions: dict[str, Question] = {}
        self._last_check_time: Optional[str] = None
        self._load()
    
    def _load(self):
        """Load questions from file."""
        if self.questions_path.exists():
            try:
                with open(self.questions_path) as f:
                    data = json.load(f)
                for q_data in data.get("questions", []):
                    q = Question(**q_data)
                    self.questions[q.id] = q
                self._last_check_time = data.get("last_check_time")
            except Exception as e:
                print(f"Warning: Could not load questions: {e}")
    
    def _save(self):
        """Save questions to file."""
        self.questions_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "questions": [asdict(q) for q in self.questions.values()],
            "last_check_time": self._last_check_time,
            "saved_at": datetime.now().isoformat()
        }
        with open(self.questions_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def ask(
        self,
        question_text: str,
        question_type: str = "free_text",
        options: Optional[list[str]] = None,
        priority: str = "medium",
        context: str = "",
        question_id: Optional[str] = None
    ) -> str:
        """
        Post a new question for the user.
        
        Args:
            question_text: The question to ask
            question_type: multiple_choice, free_text, yes_no, rating
            options: Options for multiple_choice (Other is added automatically)
            priority: low, medium, high
            context: Explanation of why the agent is asking
            question_id: Optional custom ID
        
        Returns:
            The question ID
        """
        q_id = question_id or f"q_{uuid.uuid4().hex[:8]}"
        
        # For multiple choice, always add "Other" option
        if question_type == "multiple_choice" and options:
            if "Other" not in options:
                options = options + ["Other"]
        elif question_type == "yes_no":
            options = ["Yes", "No"]
        elif question_type == "rating":
            options = ["1", "2", "3", "4", "5"]
        else:
            options = []
        
        question = Question(
            id=q_id,
            question_text=question_text,
            question_type=question_type,
            options=options,
            priority=priority,
            context=context,
            created_at=datetime.now().isoformat(),
            status="pending"
        )
        
        self.questions[q_id] = question
        self._save()
        return q_id
    
    def answer(
        self,
        question_id: str,
        answer: str,
        answer_text: Optional[str] = None
    ) -> bool:
        """
        Answer a question (called from UI).
        
        Args:
            question_id: The question to answer
            answer: The selected answer
            answer_text: Additional text for "Other" option
        
        Returns:
            True if successful
        """
        if question_id not in self.questions:
            return False
        
        q = self.questions[question_id]
        q.answer = answer
        q.answer_text = answer_text
        q.status = "answered"
        q.answered_at = datetime.now().isoformat()
        
        self._save()
        return True
    
    def check_new_answers(self) -> list[Question]:
        """
        Check for newly answered questions since last check.
        Call this at the start of each agent loop iteration.
        
        Returns:
            List of newly answered questions
        """
        new_answers = []
        check_time = datetime.now().isoformat()
        
        for q in self.questions.values():
            if q.status == "answered":
                if self._last_check_time is None or q.answered_at > self._last_check_time:
                    new_answers.append(q)
        
        self._last_check_time = check_time
        self._save()
        return new_answers
    
    def get_pending(self) -> list[Question]:
        """Get all pending questions."""
        return [q for q in self.questions.values() if q.status == "pending"]
    
    def get_answered(self) -> list[Question]:
        """Get all answered questions."""
        return [q for q in self.questions.values() if q.status == "answered"]
    
    def delete(self, question_id: str) -> bool:
        """Delete a question (usually after processing the answer)."""
        if question_id in self.questions:
            del self.questions[question_id]
            self._save()
            return True
        return False
    
    def get_all(self) -> list[Question]:
        """Get all questions."""
        return list(self.questions.values())
    
    def format_for_notification(self, questions: list[Question]) -> str:
        """Format questions for injecting into agent context."""
        if not questions:
            return ""
        
        lines = ["The user has answered your questions:"]
        for q in questions:
            answer = q.answer
            if q.answer_text:
                answer = f"{q.answer}: {q.answer_text}"
            lines.append(f"- Q: {q.question_text}")
            lines.append(f"  A: {answer}")
        
        lines.append("\nYou can delete processed questions with manage_questions(action='delete', question_id='...')")
        return "\n".join(lines)
