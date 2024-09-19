print("hello world")

import psycopg2


def insert_now():
    conn = psycopg2.connect(database='indatad_s1148232',
                            user='s1148232',
                            host='95.217.3.61',
                            password='s1148232',
                            port=5432)

    cur = conn.cursor()

    insert_query = "INSERT INTO deploy (id, deploy_timestamp) VALUES (DEFAULT, NOW())"
    cur.execute(insert_query)

    conn.commit()

    cur.close()
    conn.close()


insert_now()
