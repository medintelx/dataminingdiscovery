import sqlite3
import json
import os
import pandas as pd

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
                    examples_json TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Try adding the column if upgrading from an older schema version
            try:
                cursor.execute('ALTER TABLE questionnaires ADD COLUMN examples_json TEXT')
            except sqlite3.OperationalError:
                pass
                
            conn.commit()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quiz_scenarios (
                    concept_id TEXT PRIMARY KEY,
                    quiz_data_json TEXT,
                    ground_truth_json TEXT,
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

    def set_examples(self, examples):
        self.examples = examples

    def save_questionnaire(self):
        """Saves or updates the questionnaire in the SQLite database."""
        questions_json = json.dumps(self.questions)
        examples_json = json.dumps(getattr(self, 'examples', []))
        with sqlite3.connect(self.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO questionnaires (concept_id, questions_json, examples_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(concept_id) DO UPDATE SET
                    questions_json = excluded.questions_json,
                    examples_json = excluded.examples_json,
                    updated_at = CURRENT_TIMESTAMP
            ''', (self.concept_id, questions_json, examples_json))
            conn.commit()
        return f"Database ({self.concept_id})"

    def save_quiz_data(self, df, ground_truth):
        """Saves generated synthetic quiz data for the concept."""
        quiz_json = df.to_json(orient='records')
        gt_json = json.dumps(ground_truth)
        with sqlite3.connect(self.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO quiz_scenarios (concept_id, quiz_data_json, ground_truth_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(concept_id) DO UPDATE SET
                    quiz_data_json = excluded.quiz_data_json,
                    ground_truth_json = excluded.ground_truth_json,
                    updated_at = CURRENT_TIMESTAMP
            ''', (self.concept_id, quiz_json, gt_json))
            conn.commit()

    @staticmethod
    def load_quiz_data(concept_id):
        """Loads saved synthetic quiz data for the concept."""
        if not os.path.exists(QuestionnaireBuilder.DB_PATH):
            return None, None
            
        with sqlite3.connect(QuestionnaireBuilder.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT quiz_data_json, ground_truth_json FROM quiz_scenarios WHERE concept_id = ?", 
                (concept_id,)
            )
            row = cursor.fetchone()
            
        if row:
            df = pd.read_json(row[0], orient='records')
            gt = json.loads(row[1])
            return df, gt
        return None, None

    @staticmethod
    def load_questionnaire(concept_id):
        """Loads a questionnaire from the SQLite database."""
        if not os.path.exists(QuestionnaireBuilder.DB_PATH):
            return None
            
        with sqlite3.connect(QuestionnaireBuilder.DB_PATH) as conn:
            cursor = conn.cursor()
            # Fetch both columns, catching missing examples_json just in case schema update is pending
            try:
                cursor.execute("SELECT questions_json, examples_json FROM questionnaires WHERE concept_id = ?", (concept_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "concept_id": concept_id,
                        "questions": json.loads(row[0] or "[]"),
                        "examples": json.loads(row[1] or "[]")
                    }
            except sqlite3.OperationalError:
                # Fallback if old schema
                cursor.execute("SELECT questions_json FROM questionnaires WHERE concept_id = ?", (concept_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "concept_id": concept_id,
                        "questions": json.loads(row[0] or "[]"),
                        "examples": []
                    }
        return None
