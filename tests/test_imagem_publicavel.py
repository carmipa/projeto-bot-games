"""
Guarda de URL de imagem antes de set_image/set_thumbnail (vetor de URL do 50035).

Portado dos irmaos (anime-news/gundam) em 2026-09-18. O og:image ja passava por
validate_url_async; o caminho do FEED (entry_image_url do feed e media_thumbnail
direto) ia ao embed sem validacao. Uma URL malformada faz o Discord recusar o
embed inteiro e a noticia se perde no loop de retentativa.

Cada guarda com caso doente + caso legitimo de MESMO SINAL (regra 25/A1).
imagem_publicavel usa a parte ESTRUTURAL (sem DNS) -- seguro no event loop.
"""
from utils.security import imagem_publicavel


class TestImagemPublicavel:
    def test_doente_com_caractere_de_controle_recusada(self):
        # \n NO MEIO da URL derruba o embed (50035). Mesmo sinal do legitimo abaixo,
        # que so difere por nao ter o caractere de controle. (\n no fim e sanitizado
        # por strip -- por isso o caso perigoso e o do meio.)
        assert imagem_publicavel("https://cdn.exemplo.com/ca\npa.jpg") is None

    def test_legitimo_mesmo_host_sem_controle_passa(self):
        url = "https://cdn.exemplo.com/capa.jpg"
        assert imagem_publicavel(url) == url

    def test_doente_relativa_recusada(self):
        assert imagem_publicavel("/wp-content/capa.jpg") is None

    def test_doente_dominio_local_recusado(self):
        assert imagem_publicavel("http://localhost/x.jpg") is None

    def test_legitimo_youtube_thumb_passa(self):
        url = "https://i.ytimg.com/vi/abc/hqdefault.jpg"
        assert imagem_publicavel(url) == url

    def test_none_vazio_e_espacos_nao_levantam(self):
        assert imagem_publicavel(None) is None
        assert imagem_publicavel("") is None
        assert imagem_publicavel("   ") is None
