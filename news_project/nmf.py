# !pip3 install nbimporter
# !pip3 install nbformat
# !pip3 install sagemaker
# !pip3 install s3fs

import pandas as pd
import numpy as np
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer
from gensim.models.coherencemodel import CoherenceModel
from gensim.corpora.dictionary import Dictionary
from gensim.models.nmf import Nmf
from operator import itemgetter
import pickle
import sys
import os

from helper import word_count, process_text, topic_table, whitespace_tokenizer, unique_words, get_unstemmed_word
from predict import predict_category

def nmf(filename):
    # parameters
    # dictionary
    no_below = 10 
    no_above = 0.60 
    keep_n = 5000 
    # gensim-coherence nmf
    chunksize = 1000
    passes = 10
    kappa = 0.1
    min_prob = 0.001
    w_max_iter = 300
    w_stop_condition = 0.0001
    h_max_iter = 100
    h_stop_condition = 0.001
    eval_every = True
    # tf-idf
    min_df = 10
    max_df = 0.60
    max_features = 5000
    # sklearn-model nmf
    max_iter = 500
    tol = 0.0001

    # get data
    # df = pd.read_csv(filename)
    role = get_execution_role()
    bucket='sagemaker-studio-i7gmskjysd'
    data_key = filename
    data_location = 's3://{}/{}'.format(bucket, data_key)
    df = pd.read_csv(data_location)

    df.drop_duplicates(subset=['text'],keep='first',inplace=True)

    # process text
    df['word_count'] = df['text'].apply(word_count)
    df['processed_text'] = df['text'].apply(process_text)

    # create dictionary to pass as input to gensim model
    texts = df['processed_text']
    dictionary = Dictionary(texts)

    # filter out words 
    dictionary.filter_extremes(
        no_below=no_below,
        no_above=no_above,
        keep_n=keep_n
    )

    # convert to bag of words (corpus) to pass to gensim nmf model
    # [[(word_id, # times word appears in document),...],...]
    corpus = [dictionary.doc2bow(text) for text in texts]
  
    # find optimal # of topics
    topic_nums = list(np.arange(15,55+1,5))
    coherence_scores = []
    for num in topic_nums:
        # initialize NMF model
        nmf = Nmf(
            corpus=corpus,
            num_topics=num,
            id2word=dictionary, 
            chunksize=chunksize, 
            passes=passes, 
            kappa=kappa, 
            minimum_probability=min_prob, 
            w_max_iter=w_max_iter, 
            w_stop_condition=w_stop_condition, 
            h_max_iter=h_max_iter, 
            h_stop_condition=h_stop_condition, 
            eval_every=eval_every, 
            normalize=True, 
            random_state=42
        )

        # initialize Coherence Model
        cm = CoherenceModel(
            model=nmf,
            texts=texts,
            dictionary=dictionary,
            coherence='c_v'
        )

        coherence_scores.append(round(cm.get_coherence(), 5))

    scores = list(zip(topic_nums, coherence_scores))
    scores = sorted(scores, key=itemgetter(1), reverse=True)
    best_num_topics = scores[0][0]
    best_coherence_score = scores[0][1]
    # print('num_topics: ',str(best_num_topics))
    # print('coherence: ',str(best_coherence_score))
    # print(df.head())

    # measure of word frequency in a document (adjusted)
    min_df = no_below
    max_df = no_above
    max_features = keep_n
    tfidf_vectorizer = TfidfVectorizer(
        min_df=min_df,
        max_df=max_df,
        max_features=max_features,
        ngram_range=(1,2),
        preprocessor=' '.join
    )

    # fit+transform: returns document-term matrix (frequency of word i in document j)
    tfidf = tfidf_vectorizer.fit_transform(texts)
    # all the words we'll be looking at
    tfidf_fn = tfidf_vectorizer.get_feature_names()

    # grid search for best alpha, l1_ratio combination
    # measured by lowest sum squared residual
    # l1_ratio: regularization mixing parameter (0 => l2 penalty, 1 => l1 penalty, (0,1) => mixture)
    # alpha: constant that multiplies the regularization terms (0 => no regularization)
    squared_residuals = []
    params = {}
    models = []
    sorted_articles_dfs = []
    complete_topics_dfs = []
    alphas = list(np.arange(0.0,1.2,0.2))
    l1_ratios = list(np.arange(0.0,1.2,0.2))
    count_params = 0
    successes = 0
    count_successes = {}
    for a in alphas:
        for b in l1_ratios:
            # print('alpha: {}, l1_ratio: {}'.format(a,b))

            # learn a model
            nmf = NMF(
                n_components=best_num_topics, 
                init='nndsvd', 
                max_iter=max_iter, 
                l1_ratio=b, 
                solver='cd', 
                alpha=a, 
                tol=tol, 
                random_state=42 
            ).fit(tfidf)

            try:
                # transforms documents -> document-term matrix, transforms data according to model
                docweights = nmf.transform(tfidf) # (articles x topics)

                # topic dataframe: (best_num_topics x 8)
                # (topic num : top 8 words that describe the topic)
                n_top_words = 8
                topic_df = topic_table(
                    nmf,
                    tfidf_fn,
                    n_top_words
                ).T

                # clean the topic words
                topic_df['topics'] = topic_df.apply(lambda x: [' '.join(x)], axis=1)
                topic_df['topics'] = topic_df['topics'].str[0]
                topic_df['topics'] = topic_df['topics'].apply(lambda x: whitespace_tokenizer(x))
                topic_df['topics'] = topic_df['topics'].apply(lambda x: unique_words(x))
                topic_df['topics'] = topic_df['topics'].apply(lambda x: [' '.join(x)])
                topic_df['topics'] = topic_df['topics'].str[0]

                # clean topic dataframe 
                topic_df = topic_df['topics'].reset_index()
                topic_df.columns = ['topic_num', 'topics']

                topics = topic_df[['topic_num','topics']]
                # topics.drop_duplicates(subset=['topics'], keep='first',inplace=True)
                topics_unique = (best_num_topics - topics.shape[0]) == 0

                # assign topics to each article
                url = df['url'].tolist()
                df_temp = pd.DataFrame({
                    'url':url,
                    'topic_num':docweights.argmax(axis=1)
                })
                merged_topic = df_temp.merge(
                    topic_df,
                    on='topic_num',
                    how='left'
                )
                complete_df = merged_topic.merge(
                    df,
                    on='url',
                    how='left'
                )

                complete_df = complete_df.drop('processed_text',axis=1)
                complete_df = complete_df.drop_duplicates()
                sorted_articles = complete_df.sort_values(by=['topic_num'])

                # get num articles per topic
                num_articles_per_topic = []
                for topic in range(best_num_topics):
                    count = 0
                    for index, row in sorted_articles.iterrows():
                        if row['topic_num'] == topic:
                            count += 1
                    num_articles_per_topic.append(count)

                topics['num_articles'] = num_articles_per_topic

                # matrices from nmf (A = WH)
                mat_A = tfidf_vectorizer.transform(texts)
                mat_W = nmf.components_
                mat_H = nmf.transform(mat_A)

                # residuals: measurement of how well the topics approximate the data (observed value - predicted value)
                # 0 -> topic perfectly predicts data
                # residual = Frobenius norm tf-idf weights (A) - coefficients of topics (H) X coefficients of topics (W)
                r = np.zeros(mat_A.shape[0]) # num articles
                for row in range(mat_A.shape[0]):
                    r[row] = np.linalg.norm(mat_A[row,:] - mat_H[row,:].dot(mat_W), 'fro')

                sum_sqrt_res = round(sum(np.sqrt(r)),3)
                squared_residuals.append(sum_sqrt_res)

                # add avg residual column to topics
                complete_df['resid'] = r
                sorted_articles = complete_df.sort_values(by=['topic_num'])
                resid_data = complete_df[[
                    'topic_num','resid'
                ]].groupby('topic_num').mean().sort_values(by='resid')
                complete_topics = topics.merge(
                    resid_data,
                    on='topic_num',
                    how='left'
                )

                # save results
                sorted_articles_dfs.append(sorted_articles)
                complete_topics_dfs.append(complete_topics)
                models.append(nmf)

                count_successes[count_params] = successes
                successes += 1

            except Exception as e:
                # print('test {}, error occurred'.format(count_params))
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                print(exc_type, fname, exc_tb.tb_lineno)

            # print('test {} complete'.format(count_params)) 
            params[count_params] = (a,b)
            count_params += 1

    # find best params
    params_test = np.arange(36)
    resid_scores = list(zip(params_test,squared_residuals))
    resid_scores = sorted(resid_scores, key=itemgetter(1))
    best_params = resid_scores[0][0]
    # print('test #{} had best residual score'.format(best_params))
    # print('params: a={}, b={}'.format(params[best_params][0], params[best_params][1]))
    # print('residual scores: {}'.format(resid_scores))

    best_articles = sorted_articles_dfs[count_successes[best_params]]
    best_topics = complete_topics_dfs[count_successes[best_params]]

    best_topics = predict_category(best_topics)

    # save best topics
    for idx, row in best_topics.iterrows():
        new_words = ''
        topics_itr = row['topics'].split()
        for word in topics_itr:
            new_words += get_unstemmed_word(word) 
            new_words += ' '
        best_topics.at[idx,'topics'] = new_words

    categories = []
    for idx, row in best_articles.iterrows():
        topic_num = row['topic_num']
        topics = best_topics.at[topic_num,'topics']
        categories.append(best_topics.at[topic_num,'category'])
        best_articles.at[idx,'topics'] = topics
    best_articles['category'] = categories

    # best_articles.to_csv(path+'sorted_articles.csv',header=True)
    # best_topics.to_csv(path+'complete_topics.csv',header=True)
    data_key_articles = 'sorted_articles.csv'
    data_location_articles = 's3://{}/{}'.format(bucket, data_key_articles)
    best_articles.to_csv(data_location_articles,header=True,index=False)
    data_key_topics = 'complete_topics.csv'
    data_location_topics = 's3://{}/{}'.format(bucket, data_key_topics)
    best_topics.to_csv(data_location_topics,header=True,index=False)

    # save model
    # with open('nmf_model.pickle', 'wb') as output:
    #     pickle.dump(models[best_params], output)

    # with open('nmf_tfidf.pickle', 'wb') as output:
    #     pickle.dump(tfidf_vectorizer, output)

    s3 = boto3.client('s3')
    
    serialized_model = pickle.dumps(models[best_params])
    s3.put_object(Bucket='sagemaker-studio-i7gmskjysd', Key='nmf_model.pickle', Body=serialized_model)
    
    serialized_tfidf = pickle.dumps(tfidf_vectorizer)
    s3.put_object(Bucket='sagemaker-studio-i7gmskjysd', Key='nmf_tfidf.pickle', Body=serialized_tfidf)

filename = 'clean.csv'
# path = '/Users/miya/Documents/GitHub/ai4good_news/news_project/test_nmf'
nmf(filename)



