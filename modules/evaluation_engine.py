class EvaluationEngine:
    def __init__(self, ground_truth):
        self.ground_truth = ground_truth

    def evaluate_quiz(self, user_answers):
        """
        user_answers: list of dicts {question_idx: answer}
        """
        results = []
        score = 0
        total = len(self.ground_truth)

        for i, gt in enumerate(self.ground_truth):
            user_ans = user_answers.get(i)
            # Binary scoring for now: True if answer matches ground truth overpayment status
            # This logic assumes the question is "Is this an overpayment?"
            is_correct = False
            if user_ans == "Yes" and gt["is_overpayment"]:
                is_correct = True
            elif user_ans == "No" and not gt["is_overpayment"]:
                is_correct = True
            
            if is_correct:
                score += 1
            
            results.append({
                "row_idx": i,
                "user_answer": user_ans,
                "expected": "Yes" if gt["is_overpayment"] else "No",
                "is_correct": is_correct,
                "explanation": gt["explanation"]
            })

        percentage = (score / total) * 100 if total > 0 else 0
        return {
            "score": score,
            "total": total,
            "percentage": percentage,
            "details": results
        }
