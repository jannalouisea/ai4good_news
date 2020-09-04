import pandas as pd
import numpy as np
import csv
import json
import requests
from linkpreview import link_preview

def get_image(url):
    image = "https://sisterhoodofstyle.com/wp-content/uploads/2018/02/no-image-1.jpg"
    try:
        preview = link_preview(url)
        image = preview.image
    except requests.exceptions.HTTPError:
        pass
    except requests.exceptions.ConnectionError:
        pass
    except requests.exceptions.ReadTimeout:
        pass
    return image

def truncate_list(lst):
    return lst[:5]

data = pd.read_csv('groups/final_df.csv')
drop_idx = []

for idx, row in data.iterrows():
    lat = (row['lat']).replace('.','')
    loc = row['location']
    if not lat.isnumeric() or loc.isnumeric():
        drop_idx.append(idx)

data = data.drop(data.index[drop_idx])

world_rank = pd.read_csv('groups/worldwide.csv')
world_rank = world_rank.dropna()
canada_rank = pd.read_csv('groups/canada.csv')
canada_rank = canada_rank.dropna()
bc_rank = pd.read_csv('groups/BC.csv')
bc_rank = bc_rank.dropna()

score_len = len(world_rank.index)
world_rank = world_rank.iloc[0]
world_rank = world_rank.T
canada_rank = canada_rank.iloc[0]
bc_rank = bc_rank.iloc[0]

topic_nums = data.topic_num.unique()
topic_groups = data.groupby('topic_num')
topic_loc_df = pd.DataFrame()
for num in topic_nums:
    topic_df = topic_groups.get_group(num)
    location_groups = pd.DataFrame()

    location_groups['location'] = topic_df.groupby('location')['location'].apply(list)
    location_groups['location'] = location_groups['location'].map(lambda x: x[0])

    location_groups['topic'] = topic_df.groupby('location')['topics'].apply(list)
    location_groups['topic'] = location_groups['topic'].map(lambda x: x[0])

    location_groups['topic_num'] = topic_df.groupby('location')['topic_num'].apply(list)
    location_groups['topic_num'] = location_groups['topic_num'].map(lambda x: x[0])

    location_groups['titles'] = topic_df.groupby('location')['title'].apply(list)
    location_groups['urls'] = topic_df.groupby('location')['url'].apply(list)

    location_groups['lat'] = topic_df.groupby('location')['lat'].apply(list)
    location_groups['lat'] = location_groups['lat'].map(lambda x: x[0])

    location_groups['long'] = topic_df.groupby('location')['long'].apply(list)
    location_groups['long'] = location_groups['long'].map(lambda x: x[0])

    location_groups['category'] = topic_df.groupby('location')['category'].apply(list)
    location_groups['category'] = location_groups['category'].map(lambda x: x[0])
    
    topic_loc_df = topic_loc_df.append(location_groups)

print(topic_loc_df)

topic_loc_df['titles'] = topic_loc_df['titles'].apply(truncate_list)
topic_loc_df['urls'] = topic_loc_df['urls'].apply(truncate_list)

world_scores = []
canada_scores = []
bc_scores = []
for idx, row in topic_loc_df.iterrows():
    topic = row['topic_num']
    world_scores.append(world_rank[str(topic)])
    canada_scores.append(canada_rank[str(topic)])
    bc_scores.append(bc_rank[str(topic)])
topic_loc_df['world_score'] = world_scores
topic_loc_df['canada_score'] = canada_scores
topic_loc_df['bc_score'] = bc_scores

urls = []
for idx,row in topic_loc_df.iterrows():
    url_list = row['urls']
    image_list = []
    for url in url_list:
        image_list.append(get_image(url))
    urls.append(image_list)

topic_loc_df['image_urls'] = urls

topic_loc_df.to_csv('/Users/miya/Documents/GitHub/ai4good_news/news_project/topic_location_3.csv',index=False,header=True)


