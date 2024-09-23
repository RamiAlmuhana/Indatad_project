import paramiko
import requests
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from pytube import YouTube
import whisper
import os
import psycopg2
from datetime import datetime


def create_tables(conn):
    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS VideoStatistics_dim (
                Video_statistics_ID SERIAL PRIMARY KEY,
                Title VARCHAR(255),
                Total_views INTEGER,
                Total_likes INTEGER,
                Video_id VARCHAR(11) UNIQUE,
                Increased_views INTEGER,
                Increased_likes INTEGER
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS Transcripties_dim (
                Transcript_ID SERIAL PRIMARY KEY,
                Video_ID VARCHAR(11) REFERENCES VideoStatistics_dim(Video_id),
                Transcript TEXT
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS Date_dim (
                Datum_ID SERIAL PRIMARY KEY,
                Video_id VARCHAR(11),
                Day INTEGER,
                Month INTEGER,
                Year INTEGER
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS Video_fact (
                Video_id VARCHAR(11) PRIMARY KEY,
                Date_id INTEGER REFERENCES Date_dim(Datum_ID),
                Transcript_ID INTEGER REFERENCES Transcripties_dim(Transcript_ID),
                Video_statistics_ID INTEGER REFERENCES VideoStatistics_dim(Video_statistics_ID),
                Populariteit_score INTEGER,
                Sentiment_rating INTEGER
            );
        """)

        conn.commit()
        cur.close()
        print("Tables created successfully.")
    except Exception as e:
        conn.rollback()
        print(f"An error occurred while creating tables: {e}")


def insert_or_update_date(conn, video_id, publish_date):
    try:
        date_obj = datetime.strptime(publish_date, "%Y-%m-%dT%H:%M:%SZ")
        cur = conn.cursor()

        cur.execute("""
            SELECT Datum_ID FROM Date_dim WHERE Video_id = %s
        """, (video_id,))
        result = cur.fetchone()

        if result:
            cur.execute("""
                UPDATE Date_dim
                SET Day = %s, Month = %s, Year = %s
                WHERE Video_id = %s
            """, (date_obj.day, date_obj.month, date_obj.year, video_id))
            date_id = result[0]
        else:
            cur.execute("""
                INSERT INTO Date_dim (Video_id, Day, Month, Year)
                VALUES (%s, %s, %s, %s)
                RETURNING Datum_ID
            """, (video_id, date_obj.day, date_obj.month, date_obj.year))
            date_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        return date_id
    except Exception as e:
        conn.rollback()
        print(f"Failed to insert or update date: {e}")
        return None


def insert_or_update_video_statistics(conn, video_id, title, likes, views):
    try:
        cur = conn.cursor()

        try:
            views = int(views) if views is not None else None
        except ValueError:
            views = None

        try:
            likes = int(likes) if likes is not None else None
        except ValueError:
            likes = None

        cur.execute("""
            SELECT Video_statistics_ID, Total_views, Total_likes FROM VideoStatistics_dim WHERE Video_id = %s
        """, (video_id,))
        result = cur.fetchone()

        if result:
            current_views = result[1]
            current_likes = result[2]

            increased_views = (views - current_views) if views is not None and current_views is not None else None
            increased_likes = (likes - current_likes) if likes is not None and current_likes is not None else None

            cur.execute("""
                UPDATE VideoStatistics_dim
                SET Title = %s, Total_views = %s, Total_likes = %s, Increased_views = %s, Increased_likes = %s
                WHERE Video_id = %s
            """, (title, views, likes, increased_views, increased_likes, video_id))
            video_statistics_id = result[0]
        else:
            cur.execute("""
                INSERT INTO VideoStatistics_dim (Title, Total_views, Total_likes, Video_id)
                VALUES (%s, %s, %s, %s)
                RETURNING Video_statistics_ID
            """, (title, views, likes, video_id))
            video_statistics_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        return video_statistics_id
    except Exception as e:
        conn.rollback()
        print(f"Failed to insert or update video statistics: {e}")
        return None


def insert_or_update_transcript(conn, video_id, transcript):
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT Transcript_ID FROM Transcripties_dim WHERE Video_ID = %s
        """, (video_id,))
        result = cur.fetchone()

        if result:
            cur.execute("""
                UPDATE Transcripties_dim
                SET Transcript = %s
                WHERE Video_ID = %s
            """, (transcript, video_id))
            transcript_id = result[0]
        else:
            cur.execute("""
                INSERT INTO Transcripties_dim (Video_ID, Transcript)
                VALUES (%s, %s)
                RETURNING Transcript_ID
            """, (video_id, transcript))
            transcript_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        return transcript_id
    except Exception as e:
        conn.rollback()
        print(f"Failed to insert or update transcript: {e}")
        return None


def insert_or_update_video_fact(conn, video_id, date_id, transcript_id, video_statistics_id, popularity_score=None,
                                sentiment_rating=None):
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT Video_id FROM Video_fact WHERE Video_id = %s
        """, (video_id,))
        result = cur.fetchone()

        if result:
            cur.execute("""
                UPDATE Video_fact
                SET Date_id = %s, Transcript_ID = %s, Video_statistics_ID = %s, Populariteit_score = %s, Sentiment_rating = %s
                WHERE Video_id = %s
            """, (date_id, transcript_id, video_statistics_id, popularity_score, sentiment_rating, video_id))
        else:
            cur.execute("""
                INSERT INTO Video_fact (Video_id, Date_id, Transcript_ID, Video_statistics_ID, Populariteit_score, Sentiment_rating)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (video_id, date_id, transcript_id, video_statistics_id, popularity_score, sentiment_rating))

        conn.commit()
        cur.close()
        print(f"Video fact for {video_id} successfully saved or updated in the database.")
    except Exception as e:
        conn.rollback()
        print(f"Failed to insert or update video fact: {e}")


def fetch_youtube_metadata(api_key, video_ids):
    metadata = {}
    for video_id in video_ids:
        if len(video_id) != 11:
            print(f"Invalid video ID: {video_id}")
            continue

        url = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=snippet,statistics&key={api_key}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            if "items" in data and len(data["items"]) > 0:
                video_data = data["items"][0]
                title = video_data["snippet"]["title"]
                likes = video_data["statistics"].get("likeCount", None)
                views = video_data["statistics"].get("viewCount", None)
                publish_date = video_data["snippet"].get("publishedAt", "N/A")

                metadata[video_id] = {
                    "title": title,
                    "likes": likes if likes is not None else None,
                    "views": views if views is not None else None,
                    "publish_date": publish_date
                }
            else:
                print(f"No data found for video ID: {video_id}")
        else:
            print(f"Failed to retrieve metadata for {video_id}. Status code: {response.status_code}")

    return metadata


def list_remote_files(hostname, port, username, password, remote_directory):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(hostname, port=port, username=username, password=password)
        sftp = ssh.open_sftp()
        remote_files = sftp.listdir(remote_directory)
        return remote_files

    except Exception as e:
        print(f"An error occurred while accessing the remote server: {e}")
        return []
    finally:
        try:
            sftp.close()
        except:
            pass
        try:
            ssh.close()
        except:
            pass


def fetch_youtube_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        full_transcript = " ".join([entry['text'] for entry in transcript])
        return full_transcript
    except (TranscriptsDisabled, NoTranscriptFound):
        return None
    except Exception as e:
        print(f"Failed to fetch transcript for video ID {video_id}: {e}")
        return None


def download_youtube_video(video_id, download_path):
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(url)
        stream = yt.streams.get_lowest_resolution()
        video_file = stream.download(download_path)
        return video_file
    except Exception as e:
        print(f"Failed to download video {video_id}: {e}")
        return None


def transcribe_video_whisper(video_path):
    model = whisper.load_model("base")
    result = model.transcribe(video_path, language='english')
    return result['text']


def save_video_data(conn, video_id, title, likes, views, publish_date, transcript):
    date_id = insert_or_update_date(conn, video_id, publish_date)
    if not date_id:
        return

    video_statistics_id = insert_or_update_video_statistics(conn, video_id, title, likes, views)
    if not video_statistics_id:
        return

    transcript_id = insert_or_update_transcript(conn, video_id, transcript)
    if not transcript_id:
        return

    insert_or_update_video_fact(conn, video_id, date_id, transcript_id, video_statistics_id)


# SSH and YouTube API details
hostname = '145.97.16.170'
port = 22
username = 's1148232'
password = 's1148232'
remote_directory = '/data/video'
api_key = 'AIzaSyBS6H7B8jaUsO3uIcNgqqy1wZLVUQOSHN0'
download_path = './downloads'

# PostgreSQL database connection
conn = psycopg2.connect(
    host="95.217.3.61",
    database="indatad_s1148232",
    user="s1148232",
    password="s1148232",
    port=5432
)

create_tables(conn)

if not os.path.exists(download_path):
    os.makedirs(download_path)

file_names = list_remote_files(hostname, port, username, password, remote_directory)

youtube_metadata = fetch_youtube_metadata(api_key, file_names)

for video_id, data in youtube_metadata.items():
    transcript = fetch_youtube_transcript(video_id)

    if transcript is None:
        video_path = download_youtube_video(video_id, download_path)
        if video_path:
            transcript = transcribe_video_whisper(video_path)

    save_video_data(
        conn,
        video_id=video_id,
        title=data['title'],
        likes=data['likes'],
        views=data['views'],
        publish_date=data['publish_date'],
        transcript=transcript
    )

conn.close()
