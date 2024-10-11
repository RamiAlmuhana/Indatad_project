import os
import paramiko
import requests
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

def list_remote_files(hostname, port, username, password, remote_directory):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(hostname, port=port, username=username, password=password)
        sftp = ssh.open_sftp()
        remote_files = sftp.listdir(remote_directory)
        sftp.close()
        ssh.close()
        return remote_files
    except Exception as e:
        print(f"An error occurred while accessing the remote server: {e}")
        return []


def create_tables(conn):
    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS category_dim (
                CategoryID INT PRIMARY KEY,
                CategoryName VARCHAR(50) NOT NULL
            );
        """)

        cur.execute("SELECT COUNT(*) FROM category_dim")
        count = cur.fetchone()[0]

        if count == 0:
            print("Filling category_dim table with data...")
            cur.execute("""
                INSERT INTO category_dim (CategoryID, CategoryName) VALUES
                (1, 'Film & Animation'),
                (2, 'Autos & Vehicles'),
                (10, 'Music'),
                (15, 'Pets & Animals'),
                (17, 'Sports'),
                (18, 'Short Movies'),
                (19, 'Travel & Events'),
                (20, 'Gaming'),
                (21, 'Videoblogging'),
                (22, 'People & Blogs'),
                (23, 'Comedy'),
                (24, 'Entertainment'),
                (25, 'News & Politics'),
                (26, 'Howto & Style'),
                (27, 'Education'),
                (28, 'Science & Technology'),
                (29, 'Nonprofits & Activism'),
                (30, 'Movies'),
                (31, 'Anime/Animation'),
                (32, 'Action/Adventure'),
                (33, 'Classics'),
                (34, 'Comedy'),
                (35, 'Documentary'),
                (36, 'Drama'),
                (37, 'Family'),
                (38, 'Foreign'),
                (39, 'Horror'),
                (40, 'Sci-Fi/Fantasy'),
                (41, 'Thriller'),
                (42, 'Shorts'),
                (43, 'Shows'),
                (44, 'Trailers');
            """)
            print("category_dim table filled with data.")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS date_dim (
                date_id SERIAL PRIMARY KEY,
                year INT NOT NULL,
                month INT NOT NULL,
                day INT NOT NULL
            );
        """)

        cur.execute("SELECT COUNT(*) FROM date_dim")
        count = cur.fetchone()[0]

        if count == 0:
            print("Filling date_dim table with data...")
            cur.execute("""
                WITH RECURSIVE DateSeries AS (
                    SELECT CAST('2010-01-01' AS TIMESTAMP) AS date_value
                    UNION ALL
                    SELECT date_value + INTERVAL '1 DAY'
                    FROM DateSeries
                    WHERE date_value < TIMESTAMP '2025-12-31'
                )
                INSERT INTO date_dim (year, month, day)
                SELECT
                    EXTRACT(YEAR FROM date_value) AS year,
                    EXTRACT(MONTH FROM date_value) AS month,
                    EXTRACT(DAY FROM date_value) AS day
                FROM DateSeries
                ORDER BY date_value;
            """)
            print("date_dim table filled with data.")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS deploy_dim (
                deploy_id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_dim (
                video_id VARCHAR(11) PRIMARY KEY,
                title VARCHAR(255),
                published_date TIMESTAMP,
                tags TEXT,
                duration VARCHAR(20),
                sentiment_rating INTEGER,
                transcript TEXT
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS VideoStatistics_fact (
                video_statistics_id SERIAL PRIMARY KEY,
                date_id INTEGER REFERENCES date_dim(date_id),
                video_id VARCHAR(11) REFERENCES video_dim(video_id),
                category_id INTEGER REFERENCES category_dim(CategoryID),
                deploy_id INTEGER REFERENCES deploy_dim(deploy_id),
                total_likes INTEGER,
                previous_total_likes INTEGER,
                total_views INTEGER,
                previous_total_views INTEGER,
                total_comments INTEGER,
                previous_total_comments INTEGER,
                popularity_score INTEGER,
                previous_week_views INTEGER DEFAULT 0,
                previous_week_likes INTEGER DEFAULT 0
            );
        """)

        conn.commit()
        cur.close()
        print("All tables created and filled successfully.")
    except Exception as e:
        conn.rollback()
        print(f"An error occurred while creating or filling tables: {e}")


def insert_deploy_entry(conn):
    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO deploy_dim (timestamp)
            VALUES (CURRENT_TIMESTAMP)
            RETURNING deploy_id;
        """)

        deploy_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        print(f"deploy entry created with deploy_id: {deploy_id}")
    except Exception as e:
        conn.rollback()
        print(f"Failed to insert deploy entry: {e}")


def fetch_youtube_metadata(api_key, video_ids):
    metadata = {}
    for video_id in video_ids:
        if len(video_id) != 11:
            print(f"Invalid video ID: {video_id}")
            continue

        url = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=snippet,statistics,contentDetails&key={api_key}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            if "items" in data and len(data["items"]) > 0:
                video_data = data["items"][0]
                title = video_data["snippet"]["title"]
                published_at = video_data["snippet"].get("publishedAt", "N/A")
                category_id = video_data["snippet"].get("categoryId", None)
                tags = video_data["snippet"].get("tags", [])
                duration = video_data["contentDetails"].get("duration", "N/A")

                likes = video_data["statistics"].get("likeCount", None)
                views = video_data["statistics"].get("viewCount", None)
                comments = video_data["statistics"].get("commentCount", None)

                metadata[video_id] = {
                    "title": title,
                    "published_at": published_at,
                    "category_id": int(category_id) if category_id else None,
                    "tags": tags,
                    "duration": duration,
                    "likes": int(likes) if likes else None,
                    "views": int(views) if views else None,
                    "comments": int(comments) if comments else None
                }
            else:
                print(f"No data found for video ID: {video_id}")
        else:
            print(f"Failed to retrieve metadata for {video_id}. Status code: {response.status_code}")

    return metadata




def fetch_youtube_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        full_transcript = " ".join([entry['text'] for entry in transcript])
        return full_transcript
    except (TranscriptsDisabled, NoTranscriptFound):
        print(f"Transcripts are disabled or not available for video ID {video_id}.")
        return None
    except Exception as e:
        print(f"Failed to fetch transcript for video ID {video_id}: {e}")
        return None


def find_date_id(conn, year, month, day):
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT date_id FROM date_dim WHERE year = %s AND month = %s AND day = %s
        """, (year, month, day))
        result = cur.fetchone()
        cur.close()
        if result:
            return result[0]
        else:
            return None
    except Exception as e:
        print(f"Failed to find date_id: {e}")
        return None

def get_previous_statistics(conn, video_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT total_views, total_likes, total_comments
        FROM VideoStatistics_fact
        WHERE video_id = %s
        ORDER BY date_id DESC LIMIT 1;
    """, (video_id,))
    previous_data = cur.fetchone()
    cur.close()
    return previous_data if previous_data else (0, 0, 0)

def insert_or_update_video_dim(conn, video_id, title, published_at, transcript, sentiment_rating, tags, duration):
    try:
        published_date = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")

        cur = conn.cursor()

        cur.execute("""
            SELECT video_id FROM Video_dim WHERE video_id = %s
        """, (video_id,))
        result = cur.fetchone()

        if result:
            cur.execute("""
                UPDATE Video_dim
                SET title = %s, published_date = %s, transcript = %s, sentiment_rating = %s, tags = %s, duration = %s
                WHERE video_id = %s
            """, (title, published_date, transcript, sentiment_rating, tags, duration, video_id))
        else:
            cur.execute("""
                INSERT INTO Video_dim (video_id, title, published_date, transcript, sentiment_rating, tags, duration)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (video_id, title, published_date, transcript, sentiment_rating, tags, duration))

        conn.commit()
        cur.close()
        print(f"Video {video_id} processed and saved/updated successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Failed to insert or update video_dim: {e}")





def update_previous_week_data(conn):
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT MAX(timestamp) FROM deploy_dim
        """)
        last_deploy_timestamp = cur.fetchone()[0]

        current_time = datetime.now(timezone.utc)

        if last_deploy_timestamp:
            time_diff = current_time - last_deploy_timestamp
            if time_diff.days >= 7:
                cur.execute("""
                    UPDATE VideoStatistics_fact
                    SET previous_week_views = total_views, 
                        previous_week_likes = total_likes
                    WHERE deploy_id = (SELECT MAX(deploy_id) FROM deploy_dim);
                """)
                print("Previous week data updated successfully.")
            else:
                print("Less than 7 days since the last deploy. No update needed.")
        else:
            print("No previous deploys found. Skipping update.")

        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"Failed to update previous week data: {e}")






def insert_or_update_video_statistics_fact(conn, video_id, category_id, deploy_id, likes, views, comments):
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT published_date FROM Video_dim WHERE video_id = %s
        """, (video_id,))
        result = cur.fetchone()

        if result:
            published_date = result[0]
            cur.execute("""
                SELECT date_id FROM date_dim 
                WHERE year = %s AND month = %s AND day = %s
            """, (published_date.year, published_date.month, published_date.day))
            date_id = cur.fetchone()[0]
        else:
            print(f"No published_date found for video_id {video_id} in Video_dim.")
            return

        likes = likes if likes is not None else 0
        views = views if views is not None else 0
        comments = comments if comments is not None else 0

        previous_views, previous_likes, previous_comments = get_previous_statistics(conn, video_id)

        previous_views = previous_views if previous_views is not None else 0
        previous_likes = previous_likes if previous_likes is not None else 0
        previous_comments = previous_comments if previous_comments is not None else 0

        cur.execute("""
            SELECT video_statistics_id FROM VideoStatistics_fact WHERE video_id = %s
        """, (video_id,))
        existing_record = cur.fetchone()

        if existing_record:
            cur.execute("""
                UPDATE VideoStatistics_fact
                SET date_id = %s, category_id = %s, deploy_id = %s, total_likes = %s, total_views = %s, total_comments = %s,
                    previous_total_likes = %s, previous_total_views = %s, previous_total_comments = %s
                WHERE video_statistics_id = %s
            """, (date_id, category_id, deploy_id, likes, views, comments, previous_likes, previous_views, previous_comments, existing_record[0]))
        else:
            cur.execute("""
                INSERT INTO VideoStatistics_fact (date_id, video_id, category_id, deploy_id, total_likes, total_views, total_comments,
                                                  previous_total_likes, previous_total_views, previous_total_comments)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (date_id, video_id, category_id, deploy_id, likes, views, comments, previous_likes, previous_views, previous_comments))

        conn.commit()
        cur.close()
        print(f"Video statistics fact for video_id {video_id} saved or updated successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Failed to insert or update video statistics fact: {e}")




conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT")
)


create_tables(conn)

update_previous_week_data(conn)



insert_deploy_entry(conn)

hostname = os.getenv("SSH_HOST")
port = os.getenv("SSH_PORT")
username = os.getenv("SSH_USER")
password = os.getenv("SSH_PASSWORD")
remote_directory = os.getenv("SSH_DIRECTORY")
file_names = list_remote_files(hostname, port, username, password, remote_directory)
api_key = os.getenv("YOUTUBE_API_KEY")
youtube_metadata = fetch_youtube_metadata(api_key, file_names)

for video_id, data in youtube_metadata.items():
    category_id = data.get("category_id")
    transcript = fetch_youtube_transcript(video_id)
    sentiment_rating = 0
    tags = ", ".join(data.get("tags", []))
    duration = data.get("duration", "N/A")

    insert_or_update_video_dim(conn, video_id, data["title"], data["published_at"], transcript, sentiment_rating, tags, duration)

    cur = conn.cursor()
    cur.execute("SELECT MAX(deploy_id) FROM deploy_dim;")
    deploy_id = cur.fetchone()[0]

    insert_or_update_video_statistics_fact(conn, video_id, category_id, deploy_id, data["likes"], data["views"], data["comments"])





conn.close()
