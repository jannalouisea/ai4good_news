import pandas as pd
import pickle
from helper import get_category_name, process_text

def predict_category(df):

    # with open('svc_tfidf.pickle', 'rb') as data:
    #     tfidf = pickle.load(data)

    # with open('svc_model.pickle', 'rb') as data:
    #     model = pickle.load(data)

    s3 = boto3.client('s3')

	model_obj = s3.get_object(Bucket='sagemaker-studio-i7gmskjysd', Key='svc_model.pickle')
	serialized_model = model_obj['Body'].read()
	model = pickle.loads(serialized_model)

    tfidf_obj = s3.get_object(Bucket='sagemaker-studio-i7gmskjysd', Key='svc_tfidf.pickle')
    serialized_tfidf = tfidf_obj['Body'].read()
    tfidf = pickle.loads(serialized_tfidf)
        
    df_topics = df

    categories = []
    probabilities = []
    for idx, row in df_topics.iterrows():
        topic_matrix = tfidf.transform([row['topics']])
        topic_matrix = topic_matrix.toarray()
        svc_pred = model.predict(topic_matrix)[0]
        svc_pred_proba = model.predict_proba(topic_matrix)[0]
        category = get_category_name(svc_pred)
        probability = svc_pred_proba.max()*100
        categories.append(category)
        probabilities.append(probability)
        
    df_topics['category'] = categories
    df_topics['probability'] = probabilities

    return df_topics


def predict_topic(filename):

    # with open('nmf_model.pickle', 'rb') as data:
    #     model = pickle.load(data)

    # with open('nmf_tfidf.pickle', 'rb') as data:
    #     tfidf = pickle.load(data)

    s3 = boto3.client('s3')

    model_obj = s3.get_object(Bucket='sagemaker-studio-i7gmskjysd', Key='nmf_model.pickle')
    serialized_model = model_obj['Body'].read()
    model = pickle.loads(serialized_model)

    tfidf_obj = s3.get_object(Bucket='sagemaker-studio-i7gmskjysd', Key='nmf_tfidf.pickle')
    serialized_tfidf = tfidf_obj['Body'].read()
    tfidf = pickle.loads(serialized_tfidf)
    
    # df = pd.read_csv(filename)
    role = get_execution_role()
    bucket='sagemaker-studio-i7gmskjysd'
    data_key = filename
    data_location = 's3://{}/{}'.format(bucket, data_key)
    df = pd.read_csv(data_location)

    # process text
    df['processed_text'] = df_unseen['text'].apply(process_text)
    new_texts = df['processed_text']

    # transform data with fitted models
    tfidf_unseen = tfidf.transform(new_texts)
    X_new = model.transform(tfidf_unseen)

    # top predicted topics
    predicted_topics = [np.argsort(each)[::-1][0] for each in X_new]
    df['pred_topic_num'] = predicted_topics

    bucket='sagemaker-studio-i7gmskjysd'
    data_key = filename
    data_location = 's3://{}/{}'.format(bucket, data_key)
    df.to_csv(data_location, index=False)

# df = predict_category('test_nmf/complete_topics.csv')
# df.to_csv('topics_with_categories.csv')