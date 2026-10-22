import os 
import sys
import psycopg2 
from datasets import Dataset 
from ragas import evaluate 
from ragas.metrics import faithfullness, answer_relevance


def main():
    database_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT f.findings, f.file
        FROM findings f
        JOIN pull_requests pr ON f.pr_id = pr.id
        ORDER BY f.created_at DESC
        LIMIT 50
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print("No findings found")
        sys.exit(0)
    
    data = {
        "question": [],
        "context": [],
        "answer": [],
    }

    for message, file in rows:
        data["question"].append("what issues exist in this code?")
        data["answer"].append(message or "")
        data["context"].append([file or ""])
    
    dataset = Dataset.from_dict(data)
    results = evaluate(dataset, [faithfullness, answer_relevance])
    print(results)

    scores = results.to_pandas()
    faithfullness_score = scores["faithfullness"].mean() if "faithfullness" in scores else 1.0
    print(f"Mean Faithfullness Score: {faithfullness_score:.4f}")

    if faithfullness_score < 0.7:
        print("Faithfullness score is below 0.7, exiting")
        sys.exit(1)


if __name__ == "__main__":
    main()