import os
import sys
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
import urllib.parse as urlparse
import math
import openai
from requests.exceptions import Timeout
import logging

#API キーを取得
API_KEY = 'f96da8766da645479f4c4cd4f499b3cd'
API_BASE_URL = 'https://apim-daiwa-userapi-prod.azure-api.net'
API_VERSION = '2023-05-15'
MODEL_ID_40 = "gpt-4o-mini-2024-07-18"

# 簡易的なトークンカウントの関数（文字数ベース）
def count_tokens(text):
    return len(text)

def chunk_text(text, max_chars=60000):  # およそ15000トークンに相当する文字数
    chunks = []
    current_chunk = ""
    
    sentences = text.split(". ")
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > max_chars:
            chunks.append(current_chunk)
            current_chunk = sentence + ". "
        else:
            current_chunk += sentence + ". "
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def get_caption(url, lang):
    video_id = urlparse.parse_qs(urlparse.urlparse(url).query)['v'][0]
    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
    timestamps = list(range(0, math.ceil(transcript[-1]['start']/300)*300, 300))

    texts = []
    text = ""
    last_timestamp = 0
    for i, part in enumerate(transcript):
        minutes = math.floor(part['start'] / 60)
        seconds = int(part['start'] % 60)

        if timestamps and part['start'] >= timestamps[0]:
            texts.append(f"\n{last_timestamp}分: {text}")
            text = ""
            last_timestamp = timestamps[0]//60
            timestamps.pop(0)

        text += part['text'] + " "

    texts.append(f"\n{last_timestamp}分: {text}")
    return "".join(texts)

def revise_caption(text):
    client = openai.AzureOpenAI(
        api_key=API_KEY,
        api_version=API_VERSION,
        azure_endpoint=API_BASE_URL
    )

    def send_prompt(_user_prompt='', _system_prompt='', temperature=0):
        if not _user_prompt:
            return
        try:
            response = client.chat.completions.create(
                model=MODEL_ID_40,
                messages=[
                    {"role": "system", "content": _system_prompt},
                    {"role": "user", "content": _user_prompt}
                ],
                temperature=temperature
            )
            return response.choices[0].message.content
        except openai.APIError as e:
            logging.error(f"OpenAI API returned an API Error: {e}")
            return f"OpenAI API Error: {e}"
        except openai.AuthenticationError as e:
            logging.error(f"OpenAI API returned an Authentication Error: {e}")
            return f"Authentication Error: {e}"
        except openai.APIConnectionError as e:
            logging.error(f"Failed to connect to OpenAI API: {e}")
            return f"API Connection Error: {e}"
        except openai.InvalidRequestError as e:
            logging.error(f"Invalid Request Error: {e}")
            return f"Invalid Request: {e}"
        except openai.RateLimitError as e:
            logging.error(f"OpenAI API request exceeded rate limit: {e}")
            return f"Rate Limit Exceeded: {e}"
        except Timeout:
            logging.error("Request timed out")
            return "Timeout Error"
        except Exception as e:
            logging.error(f"Unexpected error occurred: {e}")
            return f"Unexpected Error: {e}"

    chunks = chunk_text(text)
    summaries = []
    
    for chunk in chunks:
        user_prompt = f'''
        以下の文章について、誤字と脱字を修正し、なるべく内容を削らない形でまとめてください。
        
        ###文章###
        {chunk}
        '''
        system_prompt = f'''
        あなたは優秀なスタッフです。与えられたテキストについて、
        ポイントを漏らさず伝えてください。
        '''
        summary = send_prompt(user_prompt, system_prompt)
        summaries.append(summary)
    
    # 全てのチャンクの要約を結合
    combined_summary = " ".join(summaries)
    
    # 結合した要約が長すぎる場合、再度要約
    if count_tokens(combined_summary) > 50000:
        final_user_prompt = f'''
        以下を簡潔にまとめてください。
        重要なポイントを漏らさないように注意してください。
        ###要約###
        {combined_summary}
        '''
        final_system_prompt = f'''
        あなたは優秀な要約者です。与えられた要約をさらに簡潔にまとめ、
        最も重要な情報を簡潔に伝えてください。
        '''
        final_summary = send_prompt(final_user_prompt, final_system_prompt)
        return final_summary
    else:
        return combined_summary


def main():
    try:
        logging.basicConfig(filename="logger.log", filemode='w', level=logging.INFO, format="[%(levelname)s] %(message)s", datefmt="%m/%d/%Y %I:%M:%S %p")
        logging.info("process start...")
        output_path = "./"
        url = ""
        
        # レイアウト左
        with st.sidebar:
            st.markdown("""#### 動画情報の取得""")
            with st.container():
                text_input = st.text_input("YouTubeのURL", value=url)
                lang_radio = st.radio("言語",("ja", "en"), horizontal=True)
                send_button = st.button("実行")
        # レイアウト右
        st.subheader('キャプション取得')        

        # 処理
        if send_button:
            with st.spinner("処理中..."):
                caption = get_caption(text_input, lang_radio)
                exp_1 = st.expander("オリジナル（クリックで開閉）", expanded=False)
                exp_1.write(caption)                

                rev_caption = revise_caption(caption)
                exp_2 = st.expander("修正版", expanded=True)
                exp_2.write(revise_caption(rev_caption))                
                

    except Exception as e:
        logging.error(f"エラーが発生しました: {str(e)}")
        st.error(f"エラーが発生しました: {str(e)}")

if __name__ == "__main__":
    main()
