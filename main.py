import os
import sys
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
import urllib.parse as urlparse
import math
import openai
from requests.exceptions import Timeout
import logging
import tiktoken


# Streamlit Secrets から API キーを取得
API_KEY = st.secrets["OPENAI_API_KEY"]
API_BASE_URL = st.secrets["OPENAI_API_BASE_URL"]
API_VERSION = st.secrets["OPENAI_API_VERSION"]
MODEL_ID_40 = "gpt-4o-mini-2024-07-18"
MODEL_ID_35 = "gpt-35-turbo-16k"
arg_model_id = "GPT4"

# トークンカウントの関数
def count_tokens(text):
    encoding = tiktoken.encoding_for_model("gpt-4")
    return len(encoding.encode(text))

def chunk_text(text, max_tokens=15000):
    chunks = []
    current_chunk = ""
    current_tokens = 0
    
    sentences = text.split(". ")
    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        if current_tokens + sentence_tokens > max_tokens:
            chunks.append(current_chunk)
            current_chunk = sentence
            current_tokens = sentence_tokens
        else:
            current_chunk += sentence + ". "
            current_tokens += sentence_tokens
    
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

def revise_caption(text, arg_model_id):
    openai.api_type = "azure"
    openai.api_base = API_BASE_URL
    openai.api_version = API_VERSION
    openai.api_key = API_KEY
    model_id = MODEL_ID_40

    def send_prompt(_user_prompt='', _system_prompt='', temperature=0):
        if not _user_prompt:
            return
        headers = {
            'Ocp-Apim-Subscription-Key': API_KEY,
            'Content-Type': 'application/json',
        }
        messages = [{'role':'system','content':_system_prompt},{'role':'user','content':_user_prompt}]
        try:
            response = openai.ChatCompletion.create(
                engine=model_id,
                messages = messages,
                headers = headers,
                temperature=temperature,
                timeout=500
            )
            return response['choices'][0]['message']['content']
        except openai.error.APIError as e:
            logging.error(f"OpenAI API returned an API Error: {e}")
            return f"OpenAI API Error: {e}"
        except openai.error.AuthenticationError as e:
            logging.error(f"OpenAI API returned an Authentication Error: {e}")
            return f"Authentication Error: {e}"
        except openai.error.APIConnectionError as e:
            logging.error(f"Failed to connect to OpenAI API: {e}")
            return f"API Connection Error: {e}"
        except openai.error.InvalidRequestError as e:
            logging.error(f"Invalid Request Error: {e}")
            return f"Invalid Request: {e}"
        except openai.error.RateLimitError as e:
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
        以下の文章について、日本語で要約をだしてください。
        また、誤字と脱字を修正して下さい。
        ###文章###
        {chunk}
        '''
        system_prompt = f'''
        あなたは優秀な要約者です。与えられたテキストを簡潔に要約し、
        重要なポイントを漏らさず伝えてください。
        '''
        summary = send_prompt(user_prompt, system_prompt)
        summaries.append(summary)
    
    # 全てのチャンクの要約を結合
    combined_summary = " ".join(summaries)
    
    # 結合した要約が長すぎる場合、再度要約
    if count_tokens(combined_summary) > 15000:
        final_user_prompt = f'''
        以下の要約をさらに簡潔にまとめてください。
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
                file_radio = st.radio("ファイル出力",("なし", "あり"), horizontal=True)
                text_output = st.text_input("出力先のパス", value=output_path)
                send_button = st.button("実行")
        # レイアウト右
        st.subheader(API_KEY)
        st.subheader(API_KEY)

        # 処理
        if send_button:
            with st.spinner("処理中..."):
                caption = get_caption(text_input, lang_radio)
                exp_1 = st.expander("オリジナル", expanded=False)
                exp_1.write(caption)                

                rev_caption = revise_caption(caption, arg_model_id)
                exp_2 = st.expander("要約", expanded=True)
                exp_2.write(rev_caption)
                
                if file_radio == "あり":
                    output_file = os.path.join(text_output, "caption.txt")
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(rev_caption)
                    st.success(f"ファイルを保存しました: {output_file}")

    except Exception as e:
        logging.error(f"エラーが発生しました: {str(e)}")
        st.error(f"エラーが発生しました: {str(e)}")

if __name__ == "__main__":
    main()
