# -*- coding: utf-8 -*-
"""notebook6080102acc.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/195LoOKhhHGw2vsPZsUTfMJI_GWyLWxjJ
"""

pip install catboost

pip install datasets

import sys
import gc

# Data Handling and Processing
import pandas as pd
from sklearn.model_selection import StratifiedKFold
import numpy as np

# Machine Learning Models
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from sklearn.linear_model import SGDClassifier
from sklearn.naive_bayes import MultinomialNB
from sklearn.ensemble import VotingClassifier

# Model Evaluation and Metrics
from sklearn.metrics import roc_auc_score

# Text Processing and Feature Extraction
from sklearn.feature_extraction.text import TfidfVectorizer

# Tokenizer and Preprocessing for NLP
from transformers import PreTrainedTokenizerFast
from tokenizers import (
    decoders,
    models,
    normalizers,
    pre_tokenizers,
    processors,
    trainers,
    Tokenizer,
)

# Dataset Handling and Progress Bar
from datasets import Dataset
from tqdm.auto import tqdm

test = pd.read_csv('/kaggle/input/llm-detect-ai-generated-text/test_essays.csv')
sub = pd.read_csv('/kaggle/input/llm-detect-ai-generated-text/sample_submission.csv')
org_train = pd.read_csv('/kaggle/input/llm-detect-ai-generated-text/train_essays.csv')

# Import the training set, drop any duplicates and reset the index.
train1 = pd.read_csv("/kaggle/input/daigt-v2-train-dataset/train_v2_drcat_02.csv", sep=',')
train2 = pd.read_csv('/kaggle/input/daigt-proper-train-dataset/train_drcat_04.csv')
train3 = pd.read_csv('/kaggle/input/argugpt/argugpt.csv')[['id','text','model']]

org_train = org_train.drop(columns=["prompt_id", "id"])
org_train = org_train.rename(columns={'generated': 'label'})
train1 = train1.drop(columns=["prompt_name", "source", "RDizzl3_seven"])
train2 = train2.drop(columns=["essay_id", "source", "prompt", "fold"])
train3 = train3.drop(columns=["id"])
train3 = train3.rename(columns={'model': 'label'})
train3["label"] = 1

# Concatenate them
train = pd.concat([org_train, train1, train2, train3])

# Reset index if necessary
train.reset_index(drop=True, inplace=True)
train = train.drop_duplicates(subset=['text'])
train.reset_index(drop=True, inplace=True)

# Display the first 2 rows
train.head(2)

# Sample only a portion of the training data (Used for faster testing, not final training)
# train = train.sample(frac=0.01, random_state=42)

test.head(5)

import string

# Tokenize and normalize the text
unique_words = set()
for text in train['text']:
    words = text.lower().split()  # Convert to lowercase and split into words
    unique_words.update(words)

# Remove punctuation from each word
unique_words = {word.strip(string.punctuation) for word in unique_words}

# Now, unique_words set contains all unique words
total_unique_words = len(unique_words)
print("Total unique words:", total_unique_words)

# Configuration for tokenization
LOWERCASE = False
VOCAB_SIZE = total_unique_words // 2

# Initializing the tokenizer with Byte-Pair Encoding (BPE) model.
# The [UNK] token is used to represent unknown words during tokenization.
raw_tokenizer = Tokenizer(models.BPE(unk_token="[UNK]"))

# Configuring the tokenizer's normalization and pre-tokenization steps.
# NFC normalization is applied for consistent character representation.
raw_tokenizer.normalizer = normalizers.Sequence([normalizers.NFC()] + [normalizers.Lowercase()] if LOWERCASE else [])
raw_tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel()

# Specifying special tokens for the tokenizer and initializing the BPE trainer.
# The trainer is configured with the desired vocabulary size and the special tokens.
special_tokens = ["[UNK]", "[SEP]"]
trainer = trainers.BpeTrainer(vocab_size=VOCAB_SIZE, special_tokens=special_tokens)

# Converting the test data to a Huggingface dataset for easier handling.
dataset = Dataset.from_pandas(test[['text']])

# Function to generate batches of text data for training.
# This approach helps in managing memory usage when dealing with large datasets.
def train_corp_iter():
    for i in range(0, len(dataset), 1000):
        yield dataset[i : i + 1000]["text"]

# Training the tokenizer on the dataset using the defined trainer.
raw_tokenizer.train_from_iterator(train_corp_iter(), trainer=trainer)

# Wrapping the trained tokenizer with Huggingface's PreTrainedTokenizerFast for additional functionalities.
# This step integrates the tokenizer with Huggingface's ecosystem, enabling easy use with their models.
tokenizer = PreTrainedTokenizerFast(
    tokenizer_object=raw_tokenizer,
    unk_token="[UNK]",
    sep_token="[SEP]",
)

# Tokenizing the text data in the 'test' DataFrame and storing the results.
tokenized_texts_test = []
for text in tqdm(test['text'].tolist()):
    tokenized_texts_test.append(tokenizer.tokenize(text))

# Tokenizing the text data in the 'train' DataFrame and storing the results.
tokenized_texts_train = []
for text in tqdm(train['text'].tolist()):
    tokenized_texts_train.append(tokenizer.tokenize(text))

tokenized_texts_test[1]

def dummy(text):
    """
    A dummy function to use as tokenizer for TfidfVectorizer. It returns the text as it is since we already tokenized it.
    """
    return text

# Initialize TfidfVectorizer for test set
# Parameters:
# - ngram_range=(3, 5): Use 3 to 5 word n-grams.
# - lowercase=False: Maintain case sensitivity.
# - sublinear_tf=True: Apply sublinear term frequency scaling.
# - analyzer, tokenizer, preprocessor: Use custom 'dummy' functions.
# - token_pattern=None: Disable default token pattern.
# - strip_accents='unicode': Remove accents using Unicode.
vectorizer = TfidfVectorizer(ngram_range=(3, 5), lowercase=False, sublinear_tf=True, analyzer='word',
                             tokenizer=dummy, preprocessor=dummy, token_pattern=None, strip_accents='unicode')

# Fit vectorizer on test data to learn vocabulary
vectorizer.fit(tokenized_texts_test)
vocab = vectorizer.vocabulary_  # Extract learned vocabulary

# Reinitialize TfidfVectorizer for training set using test set's vocabulary
vectorizer = TfidfVectorizer(ngram_range=(3, 5), lowercase=False, sublinear_tf=True, vocabulary=vocab,
                             analyzer='word', tokenizer=dummy, preprocessor=dummy, token_pattern=None,
                             strip_accents='unicode')

# Transform training and test data into TF-IDF vectors
tf_train = vectorizer.fit_transform(tokenized_texts_train)
tf_test = vectorizer.transform(tokenized_texts_test)

# Cleanup: Free up memory
del vectorizer
gc.collect()

# Change "tf_test.copy()" to "tf_train.copy()" to see an even clearer example of a sparse matrix.
# Set print_bool to True to print (Make sure this is False when submitting!)
print_bool = False

if print_bool:
    tf_demonstration_vector = tf_test.copy()
    tf_idf_array = tf_demonstration_vector.toarray()

    print("As can be seen, we do indeed have a sparse matrix:")
    print(type(tf_demonstration_vector), tf_demonstration_vector.shape)
    print("")
    print(tf_idf_array)

y_train = train['label'].values

if len(test.text.values) <= 5:
    sub.to_csv('submission.csv', index=False)

else:
    clf = MultinomialNB(alpha=0.02)
    sgd_model = SGDClassifier(max_iter=8000, tol=1e-4, loss="modified_huber")
    p6={'n_iter': 1500,'verbose': -1,'objective': 'binary','metric': 'auc','learning_rate': 0.05073909898961407, 'colsample_bytree': 0.726023996436955, 'colsample_bynode': 0.5803681307354022, 'lambda_l1': 8.562963348932286, 'lambda_l2': 4.893256185259296, 'min_data_in_leaf': 115, 'max_depth': 23, 'max_bin': 898}
    lgb=LGBMClassifier(**p6)
    cat=CatBoostClassifier(iterations=1000,
                           verbose=0,
                           l2_leaf_reg=6.6591278779517808,
                           learning_rate=0.005689066836106983,
                           allow_const_label=True,loss_function = 'CrossEntropy')
    weights = [0.07,0.31,0.31,0.31]

    ensemble = VotingClassifier(estimators=[('mnb',clf),
                                            ('sgd', sgd_model),
                                            ('lgb',lgb),
                                            ('cat', cat)
                                           ],
                                weights=weights, voting='soft', n_jobs=-1)
    ensemble.fit(tf_train, y_train)
    gc.collect()
    final_preds = ensemble.predict_proba(tf_test)[:,1]
    sub['generated'] = final_preds
    sub.to_csv('submission.csv', index=False)
    sub

if len(test.text.values) <= 5:
    sub.to_csv('submission.csv', index=False)

else:
    clf = MultinomialNB(alpha=0.02)
    sgd_model = SGDClassifier(max_iter=8000, tol=1e-4, loss="modified_huber")
    p6={'n_iter': 1500,'verbose': -1,'objective': 'binary','metric': 'auc','learning_rate': 0.05073909898961407, 'colsample_bytree': 0.726023996436955, 'colsample_bynode': 0.5803681307354022, 'lambda_l1': 8.562963348932286, 'lambda_l2': 4.893256185259296, 'min_data_in_leaf': 115, 'max_depth': 23, 'max_bin': 898}
    lgb=LGBMClassifier(**p6)
    cat=CatBoostClassifier(iterations=1000,
                           verbose=0,
                           l2_leaf_reg=6.6591278779517808,
                           learning_rate=0.005689066836106983,
                           allow_const_label=True,loss_function = 'CrossEntropy')
    weights = [0.07,0.31,0.31,0.31]

    ensemble = VotingClassifier(estimators=[('mnb',clf),
                                            ('sgd', sgd_model),
                                            ('lgb',lgb),
                                            ('cat', cat)
                                           ],
                                weights=weights, voting='soft', n_jobs=-1)
    ensemble.fit(tf_train, y_train)
    gc.collect()
    final_preds = ensemble.predict_proba(tf_test)[:,1]
    sub['generated'] = final_preds
    sub.to_csv('submission.csv', index=False)
    sub