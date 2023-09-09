import pandas as pd
from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
import mysql.connector
from nltk.stem.porter import PorterStemmer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity       #Finds similarity between matrices
from scipy.sparse import csr_matrix
from sklearn.neighbors import NearestNeighbors

import warnings
warnings.filterwarnings("ignore")

mydb = mysql.connector.connect(
    host = "oinvornptcknt.mysql.pythonanywhere-services.com",
    user = "oinvornptcknt", password = "w0rdpass",
    database = "oinvornptcknt$movies"
)

app = Flask(__name__)
app.config["DEBUG"] = True

#Datasets
df = pd.read_csv('/home/oinvornptcknt/mysite/movie_dataset.csv')
books = pd.read_csv('/home/oinvornptcknt/mysite/BX-Books.csv', sep=';', encoding="latin-1", error_bad_lines=False)
users = pd.read_csv('/home/oinvornptcknt/mysite/BX-Users.csv', sep=';', encoding="latin-1", error_bad_lines=False)
ratings = pd.read_csv('/home/oinvornptcknt/mysite/BX-Book-Ratings.csv', sep=';', encoding="latin-1", error_bad_lines=False)
bdf = pd.read_csv('/home/oinvornptcknt/mysite/book_dataset.csv')
music_df = pd.read_csv('/home/oinvornptcknt/mysite/final_music_dataset.csv', index_col=[0])

#Movie
ps = PorterStemmer()

def stem(text):
    y=[]

    for i in text.split():
        y.append(ps.stem(i))
    return " ".join(y)

for index,row in df.iterrows():
    df.loc[index, 'tag'] = stem(row['tag'])

cv = CountVectorizer(max_features=10000,stop_words='english')

vectors = cv.fit_transform(df['tag'])

similarity = cosine_similarity(vectors, vectors)

df = df.reset_index(drop=True)
indices = pd.Series(df.index, index=df['title'])
movie_list = [df['title'][i] for i in range(len(df['title']))]

#Book Stuff
books = books[['ISBN', 'Book-Title', 'Book-Author', 'Year-Of-Publication', 'Publisher']]
books.rename(columns = {'Book-Title':'title', 'Book-Author':'author', 'Year-Of-Publication':'year', 'Publisher':'publisher'}, inplace=True)
users.rename(columns = {'User-ID':'user_id', 'Location':'location', 'Age':'age'}, inplace=True)
ratings.rename(columns = {'User-ID':'user_id', 'Book-Rating':'rating'}, inplace=True)

x = ratings['user_id'].value_counts() > 200
y = x[x].index  #user_ids
ratings = ratings[ratings['user_id'].isin(y)]

rating_with_books = ratings.merge(books, on='ISBN')

number_rating = rating_with_books.groupby('title')['rating'].count().reset_index()
number_rating.rename(columns= {'rating':'number_of_ratings'}, inplace=True)
final_rating = rating_with_books.merge(number_rating, on='title')
final_rating.shape
final_rating = final_rating[final_rating['number_of_ratings'] >= 50]
final_rating.drop_duplicates(['user_id','title'], inplace=True)

book_pivot = final_rating.pivot_table(columns='user_id', index='title', values="rating")
book_pivot.fillna(0, inplace=True)

book_sparse = csr_matrix(book_pivot)

model = NearestNeighbors(algorithm='brute')
model.fit(book_sparse)

#General
SQLALCHEMY_DATABASE_URI = "mysql+mysqlconnector://{username}:{password}@{hostname}/{databasename}".format(
    username="oinvornptcknt",
    password="w0rdpass",
    hostname="oinvornptcknt.mysql.pythonanywhere-services.com",
    databasename="oinvornptcknt$movies",
)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_POOL_RECYCLE"] = 299
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

#This adds elements to the database using pandas, then uses mysql.connector to show it to html (so its unecessary afterwards)
engine = create_engine(SQLALCHEMY_DATABASE_URI).connect()
df.to_sql('movies', con = engine, if_exists = 'append', chunksize = 4000,index=False)
bdf.to_sql('books', con = engine, if_exists = 'append', chunksize = 4000,index=False)
music_df.to_sql('music', con = engine, if_exists = 'append', chunksize = 4000,index=False)


def recommend(movie):
    new_similarity = cosine_similarity(vectors, vectors)
    movie_idx = indices[movie]
    movies_list = list(enumerate(new_similarity[movie_idx]))
    movies_list = sorted(movies_list, key=lambda x: x[1].all(), reverse=True)
    movies_list = movies_list[1:9]
    movie_indices = [i[0] for i in movies_list]
    tit = df['title'].iloc[movie_indices]
    return_df = pd.DataFrame(columns=['title'])
    return_df = tit
    return return_df

def recommend_books(book_title):
    distances, suggestions = model.kneighbors(book_pivot.iloc[bdf[bdf['title']==book_title].index.values, :].values.reshape(1,-1))
    for i in range(len(suggestions)):
        book_arr = book_pivot.index[suggestions[i]].values
        new_bookdf = pd.DataFrame(book_arr)
        new_bookdf = new_bookdf.head()
        return new_bookdf.values

def recommend_song(song_name):
    song_name = music_df[music_df['track_name']==song_name]
    song_drop = song_name.drop('track_name', axis=1)
    song_name = pd.DataFrame(data=song_drop, index=None)
    feature_cols = music_df.drop('track_name', axis=1)
    new_X = feature_cols
    neigh = NearestNeighbors(n_neighbors=5, algorithm='kd_tree')
    neigh.fit(new_X)
    distances, indices = neigh.kneighbors(song_name)
    for i in range(len(distances.flatten())):
        return music_df['track_name'].iloc[indices[i]+1].values

@app.route("/")
def home():
    #mycursor = mydb.cursor()
    #mycursor.execute("DROP TABLE movies")

    return render_template('main_page.html')

@app.route("/movies", methods=["GET", "POST"])
def goto_movies():
    if request.method == 'GET':
        try:
            mycursor = mydb.cursor()
            mycursor.execute("SELECT DISTINCT title,genres FROM movies ORDER BY title")
            db = mycursor.fetchall()
            return render_template("movies.html", dbhtml = db)
        except Exception as e:
            return(str(e))
        else:
            return mydb

    if request.method == 'POST':
        m_name = request.form['movie_name']
        m_name = m_name.title()

        result_final = recommend(m_name)
        names = []
        for i in range(len(result_final)):
            names.append(result_final.iloc[i])

        return render_template('movie_positive.html',movie_names=names,search_name=m_name)
    return render_template('movies.html')

@app.route("/books", methods=["GET", "POST"])
def goto_books():
    if request.method == 'GET':
        try:
            mycursor = mydb.cursor()
            mycursor.execute("SELECT DISTINCT title FROM books ORDER BY title")
            db = mycursor.fetchall()
            return render_template("books.html", dbhtml = db)
        except Exception as e:
            return(str(e))
        else:
            return mydb

    if request.method == 'POST':
        b_name = request.form['book_name']
        b_name = b_name.title()

        result_final = recommend_books(b_name)
        names = []
        for i in range(len(result_final)):
            names.append(result_final[i])

        return render_template('book_positive.html',book_names=names,search_name=b_name)
    return render_template('books.html')

@app.route("/music", methods=["GET", "POST"])
def goto_music():
    if request.method == 'GET':
        try:
            mycursor = mydb.cursor()
            mycursor.execute("SELECT DISTINCT track_name,popularity FROM music ORDER BY popularity DESC LIMIT 100;")
            db = mycursor.fetchall()
            return render_template("music.html", dbhtml = db)
        except Exception as e:
            return(str(e))
        else:
            return mydb

    if request.method == 'POST':
        music_name = request.form['music_name']
        music_name = music_name.title()

        result_final = recommend_song(music_name)
        names = []
        for i in range(len(result_final)):
            names.append(result_final[i])

        return render_template('music_positive.html',music_names=names,search_name=music_name)
    return render_template('music.html')

@app.route("/food", methods=["GET", "POST"])
def goto_food():
    return render_template('food.html')