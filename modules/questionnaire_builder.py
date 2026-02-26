import sqlite3
import json
import os

class QuestionnaireBuilder:
    DB_PATH = "config/questionnaires.db"

    def __init__(self, concept_id):
        self.concept_id = concept_id
        self.questions = []
        self._init_db()

    def _init_db(self):
        """Initializes the SQLite database and creates the table if it doesn't exist."""
        os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
        with sqlite3.connect(self.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS questionnaires (
                    concept_id TEXT PRIMARY KEY,
                    questions_json TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def add_question(self, column, question_text, question_type, options=None):
        question = {
            "column": column,
            "text": question_text,
            "type": question_type,
            "options": options or []
        }
        self.questions.append(question)

    def save_questionnaire(self):
        """Saves or updates the questionnaire in the SQLite database."""
        questions_json = json.dumps(self.questions)
        with sqlite3.connect(self.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO questionnaires (concept_id, questions_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(concept_id) DO UPDATE SET
                    questions_json = excluded.questions_json,
                    updated_at = CURRENT_TIMESTAMP
            ''', (self.concept_id, questions_json))
            conn.commit()
        return f"Database ({self.concept_id})"

    @staticmethod
    def load_questionnaire(concept_id):
        """Loads a questionnaire from the SQLite database."""
        if not os.path.exists(QuestionnaireBuilder.DB_PATH):
            return None
            
        with sqlite3.connect(QuestionnaireBuilder.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT questions_json FROM questionnaires WHERE concept_id = ?", 
                (concept_id,)
            )
            row = cursor.fetchone()
            
        if row:
            return {
                "concept_id": concept_id,
                "questions": json.loads(row[0])
            }
        return None
