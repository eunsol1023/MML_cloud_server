from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import create_engine
from song2vec_data_loader import song2vec_DataLoader
from sklearn.metrics.pairwise import cosine_similarity
from django.apps import apps
from collections import Counter


engine = create_engine('mysql+pymysql://admin:pizza715@mml.cu4cw1rqzfei.ap-northeast-2.rds.amazonaws.com/mml?charset=utf8')

# DataLoader 인스턴스 생성
song2vec_data_loader = song2vec_DataLoader(engine)

mml_user_his_df, mml_music_info_df, mml_music_tag_df, music_data, music_tag_data = song2vec_data_loader.song2vec_load_data()

user_id = '08XxwFym'

def get_top_words_weights(lyrics_list, top_n=20):
    # 가사 리스트를 단어별로 펼쳐 하나의 리스트로 만듭니다.
    all_words = (word for lyrics in lyrics_list for word in lyrics)

    # 가장 빈번한 단어와 그 빈도를 계산합니다.
    top_words = Counter(all_words).most_common(top_n)

    # 가중치 정규화를 위해 최대 빈도를 구합니다.
    max_frequency = top_words[0][1] if top_words else 1

    # 단어별 가중치를 계산하여 사전 형태로 저장합니다.
    weights = {word: freq / max_frequency for word, freq in top_words}

    # 계산된 가중치를 출력합니다.
    print("Calculated Weights:", weights)

    return weights

def create_weighted_lyrics_profile(lyrics_list, w2v_model, top_words_weights):
    total_vector = None
    lyrics_count = 0

    for lyrics in lyrics_list:
        # 모델 단어장에 있는 유효한 단어만 필터링합니다.
        valid_words = [word for word in lyrics if word in w2v_model.wv]
        
        # 유효한 단어가 없으면 가사를 건너뜁니다.
        if not valid_words:
            continue

        # 가사의 각 단어에 대한 가중치가 적용된 벡터를 계산합니다.
        weighted_vectors = np.array([w2v_model.wv[word] * top_words_weights.get(word, 1) for word in valid_words])
        
        # 이 가사의 평균 벡터를 계산합니다.
        lyrics_vector = np.mean(weighted_vectors, axis=0)
        
        print("가중치가 적용된 가사 벡터:", lyrics_vector)

        # 벡터들을 집계합니다.
        if total_vector is None:
            total_vector = lyrics_vector
        else:
            total_vector += lyrics_vector

        lyrics_count += 1

    # 가사가 처리되지 않았으면 0 벡터를 반환하여 나눗셈 오류를 방지합니다.
    if total_vector is None:
        return np.zeros(w2v_model.vector_size)

    # 모든 가사에 대한 평균 벡터를 계산합니다.
    return total_vector / lyrics_count

class song2vec_view(APIView):

    def get(self, request):
        print('3번')
    
        # 모델 로드
        w2v_model = apps.get_app_config('music').model

        # 사용자별 가사 데이터 추출
        user_lyrics = music_data[music_data['user'] == user_id]['processed_lyrics']

        # 가중치 계산
        top_words_weights = get_top_words_weights(user_lyrics)

        # 가중치가 적용된 사용자 프로필 벡터 생성
        user_profile_vector = create_weighted_lyrics_profile(user_lyrics, w2v_model, top_words_weights)

        def create_lyrics_profile(lyrics_list, w2v_model):
            lyrics_vectors = []
            for lyrics in lyrics_list:
                lyrics_vector = []
                for word in lyrics:
                    if word in w2v_model.wv:  # 모델의 단어장에 있는 경우에만 처리합니다.
                        lyrics_vector.append(w2v_model.wv[word])
                if lyrics_vector:
                    lyrics_vectors.append(np.mean(lyrics_vector, axis=0))
            return np.mean(lyrics_vectors, axis=0) if lyrics_vectors else np.zeros(w2v_model.vector_size)

        # 사용자별 프로필 벡터를 생성합니다.
        # user_id = 'QrDM6lLc'
        user_lyrics = music_data[music_data['user'] == user_id]['processed_lyrics']
        user_profile_vector = create_lyrics_profile(user_lyrics, w2v_model)
        print('c')

        # 특정 사용자 ID에 대한 사용자의 청취 기록을 필터링'02FoMC0v'
        user_specific_log = music_data[music_data['user'] == user_id]

        # 특정 사용자의 장르별 플레이 횟수를 계산
        user_specific_genre_counts = user_specific_log['genre_user_log'].value_counts()

        # 특정 사용자의 상위 3개 장르를 가져옵니다.
        user_specific_top_genres = user_specific_genre_counts.head(5).index.tolist()

        # 사용자 상위 장르와 일치하는 노래에 대해 music_total_with_genre 데이터 프레임 필터링
        user_specific_top_genres_songs_df = music_tag_data[music_tag_data['genre'].isin(user_specific_top_genres)]

        # 태그 데이터를 전처리하는 함수를 정의합니다.
        def preprocess_tags(tag_string):
            # '#' 기호를 기준으로 태그를 분리합니다.
            tags = tag_string.strip().split('#')
            # 빈 문자열을 제거합니다.
            tags = [tag for tag in tags if tag]  # 공백 태그 제거
            return tags

        # 태그 데이터에 전처리 함수를 적용합니다.
        user_specific_top_genres_songs_df['processed_tags'] = user_specific_top_genres_songs_df['tag'].apply(preprocess_tags)

        # 태그를 벡터로 변환하는 함수를 정의합니다.
        def vectorize_tags(tags, w2v_model):
            tag_vectors = []
            for tag in tags:
                # 태그 내의 각 단어에 대해 벡터를 얻고 평균을 계산합니다.
                tag_word_vectors = [w2v_model.wv[word] for word in tag.split() if word in w2v_model.wv]
                if tag_word_vectors:  # 태그가 모델 단어장에 있는 경우에만 평균 벡터를 계산합니다.
                    tag_vectors.append(np.mean(tag_word_vectors, axis=0))
            return np.mean(tag_vectors, axis=0) if tag_vectors else np.zeros(w2v_model.vector_size)

        # 각 태그를 벡터로 변환합니다.
        user_specific_top_genres_songs_df['tag_vector'] = user_specific_top_genres_songs_df['processed_tags'].apply(lambda tags: vectorize_tags(tags, w2v_model))

        # 사용자 프로필 벡터와 모든 태그 벡터 사이의 코사인 유사도를 계산하고 상위 N개의 추천과 함께 유사도를 반환하는 함수
        def recommend_songs_with_similarity(user_profile_vector, tag_vectors, songs_data, top_n=20):
            # 사용자 프로필 벡터를 코사인 유사도 계산을 위해 reshape
            user_vector_reshaped = user_profile_vector.reshape(1, -1)

            # 모든 태그 벡터와의 유사도 계산
            similarity_scores = cosine_similarity(user_vector_reshaped, tag_vectors)[0]

            # 유사도 점수를 기반으로 상위 N개의 인덱스를 가져옵니다
            top_indices = similarity_scores.argsort()[-top_n:][::-1]

            # 상위 N개의 노래 추천 정보와 유사도 점수를 함께 반환
            recommendations_with_scores = songs_data.iloc[top_indices]
            recommendations_with_scores['similarity'] = similarity_scores[top_indices]
            return recommendations_with_scores[['title', 'artist', 'tag', 'similarity']]

        # 모든 태그 벡터를 하나의 배열로 추출합니다.
        tag_vectors_matrix = np.array(list(user_specific_top_genres_songs_df['tag_vector']))

        # 사용자 ID에 대한 노래 추천을 받고 유사도 점수를 포함하여 출력합니다.
        # user_profile_vector_for_similarity = user_profiles[user_id_to_recommend]  # 해당 사용자의 프로필 벡터를 가져옵니다.
        recommendations_with_similarity = recommend_songs_with_similarity(user_profile_vector, tag_vectors_matrix, user_specific_top_genres_songs_df)
        recommendations_with_similarity

        # Merge the dataframes on 'Title' and 'Artist' to find matching songs
        song2vec_final = pd.merge(
            mml_music_info_df, recommendations_with_similarity,
            on=['title', 'artist'],
            how='inner'
        )
        print('f')

        song2vec_final = song2vec_final[['title', 'artist', 'album_image_url']]

        song2vec_results=[]

        for index,row in song2vec_final.iterrows():
            result = {
                'title': row['title'],
                'artist': row['artist'],
                'image': row['album_image_url']
            }
            song2vec_results.append(result)

        return Response(song2vec_results, status=status.HTTP_200_OK)