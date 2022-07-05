## 0.0. Imports

import re
import os
import sqlite3
import logging
import requests

import pandas as pd
import numpy  as np

from datetime   import datetime
from bs4        import BeautifulSoup
from sqlalchemy import create_engine


## 1.0. Scrape Data - Showroom Products

def get_showroom_data( url, headers ):

    page = requests.get( url, headers=headers )
    soup = BeautifulSoup( page.text, 'html.parser' )

    # total of pages to iterate
    total_itens = int(soup.find_all( 'h2', class_='load-more-heading' )[0].get('data-total'))
    itens_per_page = int(soup.find_all( 'button', class_='button js-load-more' )[0].get('data-per-page'))
    page_number = int(np.ceil(total_itens / itens_per_page))

    # final request
    url2 = url + '?page-size=' + str(int (page_number * itens_per_page))
    page = requests.get(url2, headers=headers)
    soup = BeautifulSoup(page.text, 'html.parser')

    #  product id
    products = soup.find('ul', class_ = 'products-listing small')
    product_list = products.find_all('article', class_= 'hm-product-item')
    product_id = [p.get('data-articlecode') for p in product_list]

    # product name
    product_list = products.find_all('a', class_='link')
    name = [p.get_text() for p in product_list]

    # product price
    product_list = products.find_all('span', class_='price regular')
    price = [p.get_text() for p in product_list]

    data_scraped = pd.DataFrame([product_id, name, price]).T
    data_scraped.columns = ['product_id', 'name', 'price']

    # create column style_id
    data_scraped['style_id'] = data_scraped['product_id'].apply(lambda x: x[:-3])

    # drop columns with the same style_id
    data_scraped.drop_duplicates(subset=['style_id'], keep='first', inplace=True, ignore_index=True)

    return data_scraped


## 2.0. Scrape Data - Products Details

def get_product_details(data, headers):

    # iterate over product style to get product colors
    cols1 = ['product_id', 'color_name']
    df_colors = pd.DataFrame(columns=cols1)

    # iterate over product colors to get product details
    cols2 = ['length', 'waist', 'fit', 'composition', 'style', 'environmental_marker', 'product_id']
    df_details = pd.DataFrame(columns=cols2)

    count = 0
    for i in range(len(data)):
        
        # request
        url = 'https://www2.hm.com/en_us/productpage.' + data.loc[i, 'product_id'] + '.html'
        logger.debug('product: %s', url)

        page = requests.get(url, headers=headers)
        soup = BeautifulSoup(page.text, 'html.parser')
        
        # product id and color name
        product_list = soup.find_all('a', {'class':['filter-option miniature', 'filter-option miniature active']})
        product_id = [p.get( 'data-articlecode' ) for p in product_list]
        color_name = [p.get( 'data-color' ) for p in product_list]
        
        df_colors_unit = pd.DataFrame([product_id, color_name]).T
        df_colors_unit.columns = ['product_id', 'color_name']
        
        df_colors = pd.concat((df_colors, df_colors_unit), axis = 0, ignore_index=True)

        for j in range(count, len(df_colors)):

            logger.debug('color count: %s', count)

            # request
            url  = 'https://www2.hm.com/en_us/productpage.' + df_colors.loc[j, 'product_id'] + '.html'
            logger.debug('color: %s', url)
            
            page = requests.get(url, headers=headers)
            soup = BeautifulSoup(page.text, 'html.parser')
    
            count = count + 1

            # product details 
            product_atributes_list = soup.find_all('div', class_='details-attributes-list-item')

            cols = []
            details_list_unit = []  

            for p in product_atributes_list:

                    if 'messages.garmentLength' in p.get_text():
                        details_list_unit.append( p.get_text().split('\n')[2])
                        cols.append('length')

                    if 'messages.waistRise' in p.get_text():
                        details_list_unit.append( p.get_text().split('\n')[2])
                        cols.append('waist')

                    if 'Fit' in p.get_text():
                        details_list_unit.append( p.get_text().split('\n')[2])
                        cols.append('fit')

                    if 'messages.clothingStyle' in p.get_text():
                        style = p.get_text().split('\n')[2:-1]
                        details_list_unit.append(', '.join(map(str, style)))
                        cols.append('style')

                    if 'Composition' in p.get_text():   
                        composition = p.get_text().split('\n')[2:-1]
                        details_list_unit.append(', '.join(map(str, composition)))
                        cols.append('composition')

                    if 'Nice to know' in p.get_text(): 
                        details_list_unit.append(1)
                        cols.append('environmental_marker')

                    if 'Art. No.' in p.get_text():
                        details_list_unit.append( p.get_text().split('\n')[2])
                        cols.append('product_id')

            df_details_unit = pd.DataFrame(details_list_unit).T
            df_details_unit.columns = cols

            df_details = pd.concat((df_details, df_details_unit), axis = 0, ignore_index=True)

    # join df_colors and df_details
    data_products = pd.merge(df_colors , df_details[['product_id', 'length', 'waist', 'fit', 'style', 
                                                     'composition', 'environmental_marker']], how='left', on='product_id')

    # columns style_id and color_id
    data_products['style_id'] = data_products['product_id'].apply( lambda x: x[:-3] )
    data_products['color_id'] = data_products['product_id'].apply( lambda x: x[-3:] )

    # join data_products + data_scraped
    data_raw = pd.merge(data_products, data[['style_id', 'name', 'price']], how='left', on='style_id')

    # column scrapy datetime
    data_raw['scrapy_datetime'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return data_raw


## 3.0. Scrape Data - Data Cleaning

## 3.1. Helper function for data cleaning 
def get_fibers_from_compositions(data, fiber):
    df_fiber = pd.Series(dtype=object)
    for i in data.columns:
        aux  = data.loc[data[i].str.contains(fiber, na=False), i]
        df_fiber = pd.concat([df_fiber, aux], axis=0)
        df_fiber.name = fiber.replace(' ', '_')
      
    return df_fiber

## 3.2 Scrape Data - Data Cleaning
def data_cleaning(data):

    data = data.dropna(subset=['product_id'])

    # price
    data['price'] = data['price'].apply(lambda x: x.replace('$', ''))

    # name
    data['name'] = data['name'].apply(lambda x: x.replace(' ', '_').lower())

    # color_name
    data['color_name'] = data['color_name'].apply(lambda x: x.replace(' ', '_').replace('-', '_'). replace('/', '_').replace('®', '').lower())

    # style
    data['style'] = data['style'].apply(lambda x: x.replace(' ', '').replace(',', '_').replace('-', '').lower() if pd.notnull(x) else x)

    # length
    data['length'] = data['length'].apply(lambda x: x.replace('length', '').replace('-', '').lower() if pd.notnull(x) else x)

    # waist
    data['waist'] = data['waist'].apply(lambda x: x.replace('waist', '').replace('-', '').lower() if pd.notnull(x) else x)

    # fit 
    data['fit'] = data['fit'].apply(lambda x: x.replace('fit', '').replace('-', '').lower() if pd.notnull(x) else x)

    # environmental_marker
    data['environmental_marker'] = data['environmental_marker'].apply(lambda x: 0 if x != 1 else x).astype(np.int64)


    ## composition

    data['composition'] = data['composition'].astype(str)
    data['composition'] = data['composition'].apply(lambda x: x.replace('Shell: ', '') if 'Shell' in x else x)
    data['composition'] = data['composition'].apply(lambda x: re.search('.+:',   x).group(0) if ':' in x else x)
    data['composition'] = data['composition'].apply(lambda x: re.search('(.+),', x).group(1) if ':' in x else x)
    data['composition'] = data['composition'].apply(lambda x: x.lower())

    # take the name of all fibers in column composition
    aux = list(data['composition'].str.split(' ', expand=True).stack().unique())
    fibers = []

    for i in range (len(aux)):
        if ('%' not in aux[i]) & (aux[i] != 'nan') & ('other' not in aux[i])  & ('fibres' not in aux[i]):
            fibers.append(aux[i])
        elif 'other' in aux[i]:
            fibers.append('other fibres')

    # break composition by comma
    df_composition = data['composition'].str.split(',', expand=True)
    df_composition
    
    # dataframe for fibers in df_composition
    data_fibers = pd.DataFrame(index=df_composition.index)

    # apply get_fibers_from_compositions function in all fibers in df_composition
    for i in range (len(fibers)):
        data_fibers_unit = get_fibers_from_compositions(df_composition, fibers[i])
        data_fibers = pd.merge(data_fibers, data_fibers_unit, left_index=True, right_index=True, how='left')

    # format fibers columns
    for i in data_fibers.columns:
        data_fibers[i] = data_fibers[i].apply(lambda x: (int(re.search('\d+', x).group(0)) / 100) if pd.notnull(x) else x).fillna(0)
    
    # drop composition column
    data = data.drop(columns = ['composition'])

    # join datas
    data = pd.concat([data, data_fibers], axis=1)
    
    return data

def data_insertion(data):

    # create table
    query_products_schema = """
    CREATE TABLE hm_products(
        product_id           TEXT,
        price                REAL,
        name                 TEXT, 
        color_id             TEXT, 
        color_name           TEXT, 
        style_id             TEXT,
        style                TEXT,
        length               TEXT,
        waist                TEXT, 
        fit                  TEXT, 
        environmental_marker INTERGE,
        cotton               REAL, 
        spandex              REAL, 
        polyester            REAL,
        elastomultiester     REAL, 
        modal                REAL, 
        rayon                REAL, 
        copolyester          REAL, 
        elastodiene          REAL,
        lyocell              REAL,
        other_fibres         REAL,
        scrapy_datetime      TEXT
        )
    """
    conn   = sqlite3.connect('database_hm.db')
    cursor = conn.execute(query_products_schema)
    conn.commit()

    # create database connection
    conn = create_engine('sqlite:///database_hm.db', echo=False)

    # data insertion
    data.to_sql('hm_products', con=conn, if_exists='append', index=False)

    return None

def drop_duplicates_products_in_db():

    # create table 
    query_dup_products_schema = """
    CREATE TABLE dup_hm_products(
        product_id           TEXT,
        price                REAL,
        name                 TEXT, 
        color_id             TEXT, 
        color_name           TEXT, 
        style_id             TEXT,
        style                TEXT,
        length               TEXT,
        waist                TEXT, 
        fit                  TEXT, 
        environmental_marker INTERGE,
        cotton               REAL, 
        spandex              REAL, 
        polyester            REAL,
        elastomultiester     REAL, 
        modal                REAL, 
        rayon                REAL, 
        copolyester          REAL, 
        elastodiene          REAL,
        lyocell              REAL,
        other_fibres         REAL,
        scrapy_datetime      TEXT
        )
    """
    #conn   = sqlite3.connect('database_hm.db')
    #cursor = conn.execute(query_dup_products_schema)
    #conn.commit()

    # insert into dup_hm_products
    query_insert_into_dup_hm_products = """
        INSERT INTO dup_hm_products
        SELECT DISTINCT *
        FROM hm_products
        GROUP BY product_id
        HAVING COUNT(product_id) > 1
    """
    conn   = sqlite3.connect('database_hm.db')
    cursor = conn.execute(query_insert_into_dup_hm_products)
    conn.commit()

    # delete from hm_products
    query_delete_from_hm_products = """
        DELETE FROM hm_products
        WHERE product_id
        IN (SELECT product_id
        FROM dup_hm_products)
    """
    conn   = sqlite3.connect('database_hm.db')
    cursor = conn.execute(query_delete_from_hm_products)
    conn.commit()

    # insert into hm_products
    query_insert_into_hm_products = """
        INSERT INTO hm_products
        SELECT *
        FROM dup_hm_products 
    """
    conn   = sqlite3.connect('database_hm.db')
    cursor = conn.execute(query_insert_into_hm_products)
    conn.commit()

    # drop dup_hm_products
    query_drop_dup_hm_products = """
        DROP TABLE dup_hm_products
    """
    conn   = sqlite3.connect('database_hm.db')
    cursor = conn.execute(query_drop_dup_hm_products)
    conn.commit()

    return None


if __name__ == "__main__":

    # Logging
    path = ''
    if not os.path.exists(path + 'logs'):
        os.makedirs(path + 'logs')

    logging.basicConfig( 
        filename=path + 'logs/hm_etl2.log',
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')

    logger = logging.getLogger('hm_etl')

    # Parameters
    url = 'https://www2.hm.com/en_us/women/products/jeans.html'
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36"}

    # Data collection showroom
    data_collection = get_showroom_data(url, headers)
    logger.info('data collection done')

    # Data collection by product
    data_products = get_product_details(data_collection, headers)
    logger.info('data by product done')
    
    # Data cleaning
    data_products_cleaned = data_cleaning(pd.read_csv('df_products_raw5.csv'))
    logger.info('data cleaning done')

    # Data insertion
    data_insertion(pd.read_csv('data_cleaned.csv'))
    logger.info('data insertion done')

    # Drop duplicates on DB
    drop_duplicates_products_in_db()
    logger.info('drop duplicates products in db done')

