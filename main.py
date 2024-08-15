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

def revise_caption(text):
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
        st.subheader('キャプション取得') 

        # 処理
        if send_button:
            with st.spinner("処理中..."):
                caption = get_caption(text_input, lang_radio)
                exp_1 = st.expander("オリジナル", expanded=False)
                exp_1.write(caption)                

                rev_caption = revise_caption(caption)
                exp_2 = st.expander("要約", expanded=True)
                text = "嵐の始まりは今から2週間前日銀上田総裁 のこの発言でした引き続き金利を上げて いくでその際に0.5は壁として意識さ れるかという質問だったと思いますがそこ はあの特に意識しておりません上田総裁の 強気とも取れる発言もあってか翌日の日経 平均株価は1000円近い 楽一方アメリカでは FRBが次回9月のFOMCでの利下げを 示雇用統計の内容も市場の予想より悪かっ たことからアメリカの景気交代への懸念が 高まりダは600ドルを超える大幅安 さらに急速に円高が進みました 明けた先週の 月曜いやびっっくりしたね15 % やばい今月5日の日経平均株価は 4451安と市場最大の下げ幅を記録し まし たその2日 後利上げについて慎重に考えるべき要素が え 承知たという風に言わざる得ない と日銀内田副総裁の今後の利上げには新調 という発言でマーケットに安心感が広がり この日の日経平均株価は1100円以上 上げる場面がありまし たその後も変動を続けながら今日は 3万6000円台で取引を終えています マーケットを襲った嵐は去ったのか専門家 と考えます日銀の追加利上げそして アメリカの雇用統計の指標の悪化などを 受け日経平均株価は大きく下げました5日 に過去最大の下落幅を記録ただその後なん ですが戻り補聴ということですえまずは コルさんここ2週間の急激な変動ですね嵐 は収まったと見ていいんでしょうか私は そうと思うんですけれどもだ必ずですね やっぱりシキはシキであってでもやっぱり あのその市ま株式市場はボラティリティが ないと儲からないわけなんですけれども ですね変がやっぱり大きくなってとこれは 必ずシキなんですけれどもでもやっぱり 根本的には日本企業は非常に強いんですよ 設備投資もやったりとかあのその実質金利 もあの実質金利じゃなくてあの実質あの 賃金もやっぱり上昇してるとか株主元 やっぱりもしっかりしてやってだからこそ やっぱりあの今会のチャンスではないかと 思いますうん小林さんはいかがですかはい あの経済や企業のファンダメンタルズが 変わってない中でということなのでま今回 の作業はやりすぎだったとでそこからの 回復過程にあるっていうのは全く同じ意見 ですとただまあまりにもですねま ボラティリティ市場の変動が大きかった せいでまやはり取れるリスクが取りにくく なっているというのがま多くの投資家の 現状ではないかと思いますなのでま一言で 言えば上がりみたいな状況まこのまま何も なくですね大下なく過ぎていけば回復して いくわけですけれどもしかし変な ボラティリティがまた出てきてしまうと 下げるリスクは普段よりちょっと高いそう いう状況ではないかなと思ってますま イベントとしては太め要因まだまだあり ますからねその辺りをどうこなしていくか ということだと思うんですが波乱の最初の きっかけと言われているのが先月末の日銀 の追加利上げです上田総裁の今後の利上げ についてもえの姿勢を示したんですが マーケットの同様があった後の内田副総裁 の発言では慎重な姿勢を見せましたうん 小林さんはその今回のマーケットの同様の 主な要因としてこの日銀の政策変更があっ たという風に見ていますかはい元々その 射撃長に入っていったのは7月の頭からと いうことですからま日銀については主因と いうよりもその流れにとどめをさしたと いうところだったんではないかなというふ に思いますでただですね利上げをしたと 言ってもたった0.15%ポイントという ことですからこれがとめをさしたという ことは多分ないむしろどちらかというと今 までおっしゃっていた政策の方針と今回の 方針っていうのはかなりガラっとか変わっ たように感じられたとま例えば4月には 156NH1156NHだった時に円安の 影響は物価に対してそんなにえ大きくない ということをおっしゃってわけですけれど も今回の政策変更あるいは今後の政策 \n5分: 円安での上りリスクが大きいと153で 書かれていたというところもありますとま それ以外にも色々ですねあの今回かなり こう大きく変わる部分が多かったという ところでマーケットがびっくりしたという ことではないかなと思いますま面白くて やっぱりまずウラ総裁の日本銀行は正しい ことをやってるんですよだって資本主義 自由経済であるとゼロ金利はありえない うんあるいは国際はもうほぼほぼ中央銀行 を買ってくれるという国はこれは重世界重 資本主義ではありませんだからやってる ことは間違いなくて正しいんですよ正常化 に向けてということですそうそういうこと なんですけど問題はやっぱりどうしても コミュニケーションはですね今回は ちょっとですねやっぱりあの強すぎて 例えばですねじゃあその国際あのね6兆円 からあのあの3兆円しか買わないという 発言なんですけれどもこれはハードな数字 目標なんですよ例えばフェデラルリザーブ 同じ量的管の廃止テポリンが始まった時に は1回にもハードな数字を出してくれ なかったんですけれどもだからその支場の 観点から見るとですねやっぱり今まで行っ てきた1年半"
                exp_2.write(revise_caption(text))
                
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
