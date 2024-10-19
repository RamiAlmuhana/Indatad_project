import os

import pandas as pd
import psycopg2
import joblib
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


def load_model_and_vectorizer():
    classificatie_model = joblib.load('classificatie_model.pkl')
    Nlp_model = joblib.load('Nlp_model.pkl')
    return classificatie_model, Nlp_model


def get_video_data(engine):
    query = """
    SELECT video_id, title, published_date, tags, duration, sentiment_rating, transcript 
    FROM public.video_dim;
    """
    df = pd.read_sql(query, engine)
    return df


def calculate_sentiment(df, classificatie_model, Nlp_model):
    df['transcript'] = df['transcript'].fillna('')

    transcript_bow = Nlp_model.transform(df['transcript'].tolist())

    sentiment_predictions = classificatie_model.predict(transcript_bow)

    df['sentiment_rating'] = sentiment_predictions
    df['sentiment_rating'] = df['sentiment_rating'].apply(lambda x: 'Positive' if x == 1 else 'Negative')
    return df


def update_sentiment_in_db(df):
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )

    cur = conn.cursor()

    for index, row in df.iterrows():
        query = """
        UPDATE public.video_dim
        SET sentiment_rating = %s
        WHERE video_id = %s;
        """
        cur.execute(query, (row['sentiment_rating'], row['video_id']))

    conn.commit()
    cur.close()
    conn.close()


def main():
    engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

    classificatie_model, Nlp_model = load_model_and_vectorizer()

    df = get_video_data(engine)

    if df.empty:
        print("Alle videos hebben al een sentiment_rating.")
        return

    df = calculate_sentiment(df, classificatie_model, Nlp_model)

    update_sentiment_in_db(df)

    print("Sentiment_rating toegevoegd")


if __name__ == "__main__":
    main()
