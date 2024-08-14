import os
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
import urllib.parse as urlparse
import math
import openai
from requests.exceptions import Timeout
import logging


# Streamlit Secrets から API キーを取得
try:
    API_KEY = st.secrets["OPENAI_API_KEY"]
    API_BASE_URL = st.secrets["OPENAI_API_BASE_URL"]
    API_VERSION = st.secrets["OPENAI_API_VERSION"]
except:
    API_KEY = os.environ.get('OPENAI_API_KEY')
    API_BASE_URL = os.environ.get('OPENAI_API_BASE_URL')
    API_VERSION = os.environ.get('OPENAI_API_VERSION')
    
MODEL_ID_40 = "gpt-4o-ptu"
MODEL_ID_35 = "gpt-35-turbo-16k"


def get_caption(url, lang):
    video_id = urlparse.parse_qs(urlparse.urlparse(url).query)['v'][0]
    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
    # 5分ごとのタイムスタンプを格納するリストを初期化
    timestamps = list(range(0, math.ceil(transcript[-1]['start']/300)*300, 300))

    # 各部分のトランスクリプトをループで処理
    texts = []
    text = ""
    last_timestamp = 0
    for i, part in enumerate(transcript):
        # 各部分の開始時間（タイムスタンプ）を分表記に変換
        minutes = math.floor(part['start'] / 60)
        seconds = int(part['start'] % 60)

        # 5分ごとのタイムスタンプを表示
        if timestamps and part['start'] >= timestamps[0]:
            texts.append(f"\n{last_timestamp}分: {text}")
            # print(f"\n{last_timestamp}分: {text}")
            text = ""
            last_timestamp = timestamps[0]//60
            timestamps.pop(0)

        # 各部分のテキストをまとめる
        text += part['text'] + " "

    # 最後のテキストを表示
    texts.append(f"\n{last_timestamp}分: {text}")
    # print(f"\n{last_timestamp}分: {text}")
    # return "".join(texts[1:])
    return "".join(texts) # TODO

def revise_caption(text, arg_model_id):

    openai.api_type = "azure"
    openai.api_base = API_BASE_URL
    openai.api_version = API_VERSION
    openai.api_key = API_KEY
    model_id = MODEL_ID_40 if arg_model_id=="GPT4" else MODEL_ID_35

    def send_prompt(_user_prompt='', _system_prompt='', temperature=0):
        if not _user_prompt:
            return
        headers = {
            'Ocp-Apim-Subscription-Key':API_KEY,
            'Content-Type':'application/json',
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
        except Timeout:
            return "Timeout Error"
        except Exception as e:
            return f"Error: {str(e)}"

    user_prompt = f'''
    以下の文章について、日本語で要約をだしてください。
    また、誤字と脱字を修正して下さい。
    ###文章###
    {text}
    '''
    system_prompt = f'''
    '''
    res = send_prompt(user_prompt, system_prompt)
    return res

def main():
    try:
        log_path = os.path.join(os.path.dirname(__file__), "logger.log")
        logging.basicConfig(filename=log_path, filemode='w', level=logging.INFO, format="[%(levelname)s] %(message)s", datefmt="%m/%d/%Y %I:%M:%S %p")
        logging.info("process start...")
        output_path = "./"
        url = ""
        
        # レイアウト左
        with st.sidebar:
            st.markdown("""#### 動画情報の取得""")
            with st.container():
                text_input = st.text_input("YouTubeのURL", value=url)
                lang_radio = st.radio("言語",("ja", "en"), horizontal=True)
                file_radio = st.radio("ファイル出力",("あり", "なし"), horizontal=True)
                text_output = st.text_input("出力先のパス", value=output_path)
                model_radio = st.radio("モデル",("GPT3.5", "GPT4"), horizontal=True, index=1)
                send_button = st.button("実行")
        # レイアウト右
        st.subheader("キャプション取得")

        # 処理
        if send_button:
            with st.spinner("処理中..."):
                caption = get_caption(text_input, lang_radio)
                exp_1 = st.expander("オリジナル", expanded=False)
                exp_1.write(caption)                

                rev_caption = revise_caption(caption, model_radio)
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
