import os

import pandas as pd
import psycopg2
import joblib
from datetime import datetime
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()


def fetch_videos_without_popularity(engine):
    query = """
    SELECT vsf.video_id, vsf.total_views, vsf.total_likes, vd.title, vd.published_date 
    FROM VideoStatistics_fact vsf
    JOIN video_dim vd ON vsf.video_id = vd.video_id
    WHERE vsf.popularity_score IS NULL;
    """
    return pd.read_sql(query, engine)


def preprocess_data(df):
    df['likes_to_views'] = df['total_likes'].astype(float) / df['total_views'].astype(float)
    df['title_length'] = df['title'].apply(len)
    df['published_date'] = pd.to_datetime(df['published_date'])
    df['days_since_published'] = (pd.Timestamp.today().tz_localize(None) - df['published_date']).dt.days
    df['days_since_published'] = df['days_since_published'].replace(0, 1)
    df['published_Year'] = df['published_date'].dt.year
    return df


def predict_popularity(df, scaler, kmeans_model):
    features = ['likes_to_views', 'title_length', 'days_since_published', 'published_Year']
    scaled_data = pd.DataFrame(scaler.transform(df[features]), columns=features)
    predictions = kmeans_model.predict(scaled_data)
    df['popularity_score'] = predictions
    df['popularity_score'] = df['popularity_score'].apply(lambda x: 'Popular' if x == 1 else 'Not Popular')
    return df


def update_database_with_predictions(df, conn):
    cur = conn.cursor()
    for index, row in df.iterrows():
        query = """
        UPDATE VideoStatistics_fact
        SET popularity_score = %s
        WHERE video_id = %s;
        """
        cur.execute(query, (row['popularity_score'], row['video_id']))
    conn.commit()
    cur.close()


def main():
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")

    engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

    df = fetch_videos_without_popularity(engine)

    if not df.empty:
        df = preprocess_data(df)

        kmeans_model = joblib.load('kmeans_model.joblib')
        scaler = joblib.load('scaler.joblib')

        df = predict_popularity(df, scaler, kmeans_model)

        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )

        update_database_with_predictions(df, conn)

        conn.close()

        print("Popularity toegevoegd")
    else:
        print("Alle videos hebben 'popularity_score'")


if __name__ == '__main__':
    main()
