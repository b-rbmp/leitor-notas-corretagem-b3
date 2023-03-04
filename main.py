
import datetime
from io import StringIO
import os
import shutil
import pandas as pd
import re
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfinterp import resolve1
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser

from typing import List, Tuple
from pydantic import BaseModel

from especificacoes import especificacoes

PASTA_NOTAS = "notas/"
PASTA_NAO_PROCESSADOS = PASTA_NOTAS+"nao_processados/"
PASTA_PROCESSADOS = PASTA_NOTAS+"processados/"

class NotaCorretagemTratamento(BaseModel):
    texto: str
    file_path: str

class Operacao(BaseModel):
    ativo: str
    data: str
    tipoOp: str
    quantidade: int
    preco: float
    valor: float
    taxas: float
    corretora: str
    irpf: float
    mercado: str
    daytrade: bool

class NotaCompilada(BaseModel):
    corretora: str
    data: str
    nr_nota: str
    compras: float = 0.00
    vendas: float = 0.00
    volume: float = 0.00
    irpf: float | None = None
    taxas: float | None = None
    liquido: float | None = None
    operacoes_compiladas: List[Operacao] = []

# Create a folder "notas" if it doesn't exist, with subfolders "processados" and "nao_processados". Create a folder "output" if it doesn't exist
def setup_folders():
    if not os.path.exists(PASTA_NOTAS):
        os.mkdir(PASTA_NOTAS)
    if not os.path.exists(PASTA_NAO_PROCESSADOS):
        os.mkdir(PASTA_NAO_PROCESSADOS)
    if not os.path.exists(PASTA_PROCESSADOS):
        os.mkdir(PASTA_PROCESSADOS)
    if not os.path.exists("output"):
        os.mkdir("output")


# Open the file and extract invoices from all pages, in string format
def extract_invoices_from_pdf(pdf_path: str) -> List[NotaCorretagemTratamento]:
    nota_corretagens: List[NotaCorretagemTratamento] = []

    text_buffer: str = ''  # Buffer de texto zerado a cada fatura nova encontrada num mesmo arquivo
    with open(pdf_path, 'rb') as in_file:
        parser = PDFParser(in_file)
        doc = PDFDocument(parser)

        pages = PDFPage.get_pages(in_file)

        count = 0  # Contagem das páginas

        number_of_pages = resolve1(doc.catalog['Pages'])['Count']
        for num, page in enumerate(pages):
            if num == count:
                output_string = StringIO()
                rsrcmgr = PDFResourceManager()
                device = TextConverter(rsrcmgr, output_string, laparams=LAParams(char_margin=350, boxes_flow=None))
                interpreter = PDFPageInterpreter(rsrcmgr, device)

                interpreter.process_page(page)

                text = output_string.getvalue()

                pagina_inicial = re.search('NOTA DE NEGOCIAÇÃO', text)
                is_pagina_inicial = True if pagina_inicial is not None else False

                if is_pagina_inicial:
                    if text_buffer != '':
                        dado_corretagem = NotaCorretagemTratamento(texto=text_buffer, file_path=pdf_path)
                        nota_corretagens.append(dado_corretagem)
                    text_buffer = ''

                text_buffer += text

                if num == number_of_pages - 1:
                    if text_buffer != '':
                        dado_corretagem = NotaCorretagemTratamento(texto=text_buffer, file_path=pdf_path)
                        nota_corretagens.append(dado_corretagem)
            count += 1
    return nota_corretagens

# Encontra a corretora da nota de corretagem
def find_corretora(texto: str):
    if re.search('Rico Investimentos', texto):
        return "RICO"
    elif re.search('CLEAR', texto):
        return "CLEAR"
    else:
        raise Exception("Corretora não encontrada")

def get_nota_number_inside_nota_list(nota_number: str, nota_list: List[NotaCompilada]) -> None | int:
    for index, nota in enumerate(nota_list):
        if nota.nr_nota == nota_number:
            return index
    return None

def find_ticker_by_especificacao(especificacao: str):
    ticker = ""
    for especificacao_key, especificacao_value in especificacoes.items():
        if re.search(especificacao_key, especificacao, re.IGNORECASE):
            ticker = especificacao_value
            break

    if ticker == "":
        raise Exception("Ticker não encontrado")
    
    aditivo = None
    if re.search("ON", especificacao, re.IGNORECASE):
        aditivo = "3"
    elif re.search("PNA", especificacao, re.IGNORECASE):
        aditivo = "5"
    elif re.search("PNB", especificacao, re.IGNORECASE):
        aditivo = "6"
    elif re.search("PN", especificacao, re.IGNORECASE):
        aditivo = "4"
    elif re.search("UNT", especificacao, re.IGNORECASE):
        aditivo = "11"
    elif re.search("CI", especificacao, re.IGNORECASE):
        aditivo = "11"
    elif re.search("FII ", especificacao, re.IGNORECASE):
        aditivo = "11"
    elif re.search("F11", especificacao, re.IGNORECASE):
        aditivo = "11"
    elif re.search("DO", especificacao, re.IGNORECASE):
        aditivo = "1"
    else:
        raise Exception("Aditivo não encontrado")
    
    ticker = ticker + aditivo
    return ticker.upper()
    
# From a list of NotaCompilada, create a dataframe with all operations and return it
def get_dataframe_from_list_notacompilada(nota_list: List[NotaCompilada]) -> pd.DataFrame:
    data = []
    for nota in nota_list:
        for operacao in nota.operacoes_compiladas:
            sinal_qtd = 1 if operacao.tipoOp == "C" else -1
            data.append({
                "ativo": operacao.ativo,
                "data": nota.data,
                "tipoOp": operacao.tipoOp,
                "quantidade": sinal_qtd*operacao.quantidade,
                "preco": str(operacao.preco).replace(".", ","),
                "taxas": str(operacao.taxas).replace(".", ","),
                "corretora": nota.corretora,
                "irpf": str(operacao.irpf).replace(".", ","),
                "nr_nota": nota.nr_nota,
                "valor": str(operacao.valor).replace(".", ","),
                "mercado": operacao.mercado,
                "daytrade": operacao.daytrade,
            })
    return pd.DataFrame(data)

def tratamento_texto_nao_processados():
    # Get all files inside subdirectory
    filelist = []
    for root, dirs, files in os.walk(PASTA_NAO_PROCESSADOS):
        for file in files:
            #append the file name to the list, if pdf
            if file.endswith('.pdf'):
                filelist.append(os.path.join(root,file))

    # Guarda informação sobre a file location e texto para cada arquivo
    fileinfos: List[Tuple[str, str]] = []
    notas_corretagens: List[NotaCorretagemTratamento] = []
    for file in filelist:
        notas_corretagens_item = extract_invoices_from_pdf(file)
        notas_corretagens.extend(notas_corretagens_item)
    
    notas_compiladas: List[NotaCompilada] = []
    for nota_corretagem in notas_corretagens:
        
        is_nota_bmef = True if re.search('BM&F', nota_corretagem.texto) else False
        
        numero_nota = re.search('Nr. nota\n\nFolha\n\nData pregão\n\n(\d+)\n\n', nota_corretagem.texto)
        if numero_nota is None:
            numero_nota = re.search('Nr. nota\n\n([\d\.]+)\n\n', nota_corretagem.texto)
        if numero_nota is not None:
            numero_nota = numero_nota.group(1)
        else:
            for i in range(1, 100):
                if get_nota_number_inside_nota_list(str(i), notas_compiladas) is None:
                    numero_nota = str(i)
                    break

        nota_exists_index = get_nota_number_inside_nota_list(numero_nota, notas_compiladas)
        if nota_exists_index is not None:
            corretora = notas_compiladas[nota_exists_index].corretora
            data_nota = notas_compiladas[nota_exists_index].data

            if notas_compiladas[nota_exists_index].irpf is None:
                irpf_nota = re.search('\n(-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*)I.R.R.F.', nota_corretagem.texto)
                if irpf_nota is None:
                    irpf_nota = re.search('IRRF operacional .*\n\n(-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) ', nota_corretagem.texto)
                if irpf_nota is not None:
                    notas_compiladas[nota_exists_index].irpf = float(irpf_nota.group(1).replace('.', '').replace(',', '.'))
            if notas_compiladas[nota_exists_index].liquido is None:
                liquido_nota = re.search('[DC]\n(-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*).*Líquido para .+([DC])', nota_corretagem.texto)
                if liquido_nota is not None:
                    liquido_nota_valor = liquido_nota.group(1)
                    liquido_nota_valor = liquido_nota_valor.replace(".", "")
                    liquido_nota_valor = liquido_nota_valor.replace(",", ".")
                    liquido = float(liquido_nota_valor)
                    if liquido_nota.group(4) == "D":
                        liquido = liquido * -1
                    notas_compiladas[nota_exists_index].liquido = liquido
                if liquido_nota is None:
                    liquido_nota = re.search(' ([0-9]+(\.[0-9]{3})*(,[0-9]+)?) \| ([DC]) \n\n\+Custos BM&F', nota_corretagem.texto)
                    if liquido_nota is not None:
                        liquido_nota_valor = liquido_nota.group(1)
                        liquido_nota_valor = liquido_nota_valor.replace(".", "")
                        liquido_nota_valor = liquido_nota_valor.replace(",", ".")
                        liquido = float(liquido_nota_valor)
                        if liquido_nota.group(4) == "D":
                            liquido = liquido * -1
                        notas_compiladas[nota_exists_index].liquido = liquido


        else: 
            corretora = find_corretora(nota_corretagem.texto)
            data_nota = ""
            data_nota_find = re.search('([0-9]{2}/[0-9]{2}/[0-9]{4})\n\nRico', nota_corretagem.texto)
            if data_nota_find is None:
                data_nota_find = re.search('([0-9]{2}/[0-9]{2}/[0-9]{4})\n\nCLEAR', nota_corretagem.texto)

            if data_nota_find is None:
                data_nota_find = re.search('Data pregão\n([0-9]{2}/[0-9]{2}/[0-9]{4})\n\n', nota_corretagem.texto)
            if data_nota_find is not None:
                data_nota = data_nota_find.group(1)
            else:
                raise Exception("Data da nota não encontrada")

            nota_compilada = NotaCompilada(nr_nota=numero_nota, corretora=corretora, data=data_nota)


            irpf_nota = re.search('\n(-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*)I.R.R.F.', nota_corretagem.texto)
            if irpf_nota is None:
                irpf_nota = re.search('IRRF operacional .*\n\n(-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) ', nota_corretagem.texto)
            if irpf_nota is not None:
                nota_compilada.irpf = float(irpf_nota.group(1).replace('.', '').replace(',', '.'))

            liquido_nota = re.search('[DC]\n(-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*).*Líquido para .+([DC])', nota_corretagem.texto)
            if liquido_nota is not None:
                liquido_nota_valor = liquido_nota.group(1)
                liquido_nota_valor = liquido_nota_valor.replace(".", "")
                liquido_nota_valor = liquido_nota_valor.replace(",", ".")
                liquido = float(liquido_nota_valor)
                if liquido_nota.group(4) == "D":
                    liquido = liquido * -1
                nota_compilada.liquido = liquido
            if liquido_nota is None:
                liquido_nota = re.search(' ([0-9]+(\.[0-9]{3})*(,[0-9]+)?) \| ([DC]) \n\n\+Custos BM&F', nota_corretagem.texto)
                if liquido_nota is not None:
                    liquido_nota_valor = liquido_nota.group(1)
                    liquido_nota_valor = liquido_nota_valor.replace(".", "")
                    liquido_nota_valor = liquido_nota_valor.replace(",", ".")
                    liquido = float(liquido_nota_valor)
                    if liquido_nota.group(4) == "D":
                        liquido = liquido * -1
                    nota_compilada.liquido = liquido



            notas_compiladas.append(nota_compilada)
   
        mercado = ""

        tamanho_notas_compiladas = len(notas_compiladas)

        if is_nota_bmef:
            mercado = "BM&F"

            taxa_bmef = re.search('(-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) \| D \n\nOutros', nota_corretagem.texto)
            if not taxa_bmef:
                raise Exception("Taxa BM&F não encontrada")
            taxa_bmef_valor = float(taxa_bmef.group(1).replace('.', '').replace(',', '.'))
            notas_compiladas[tamanho_notas_compiladas-1].taxas = taxa_bmef_valor

            # Pega o IRPF Projetado, pois é subtraido pela corretora, diferentemente da B3
            irpf_projetado = re.search('\|  (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*)  (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*)  (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*)  (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) \| [DC]', nota_corretagem.texto)
            if not irpf_projetado:
                raise Exception("IRPF Projetado não encontrado")
            irpf_projetado_valor = float(irpf_projetado.group(1).replace('.', '').replace(',', '.'))
            notas_compiladas[tamanho_notas_compiladas-1].irpf = irpf_projetado_valor
            
            linhas = re.findall(r'\n([CV] .*)', nota_corretagem.texto)
            if linhas is None:
                raise Exception("Não foi possível encontrar as linhas da nota")
            for linha in linhas:
                op = linha[0]

                grupos = re.search(r'[CV] (.+) @?([0-9]{2}/[0-9]{2}/[0-9]{4}) (\d) (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) (.+) (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) ([CD]) (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*)', linha, re.IGNORECASE)
                if grupos is None:
                    raise Exception("Não foi possível encontrar os grupos da linha")
                ticker = grupos.group(1)
                quantidade = float(grupos.group(3))
                preco = float(grupos.group(4).replace('.', '').replace(',', '.'))
                daytrade = True if grupos.group(7) == "DAY TRADE" else False
                valor = float(grupos.group(8).replace('.', '').replace(',', '.'))
                credito_debito = grupos.group(11)
                notas_compiladas[tamanho_notas_compiladas-1].volume = notas_compiladas[tamanho_notas_compiladas-1].volume + abs(valor)
                if op == 'C':
                    notas_compiladas[tamanho_notas_compiladas-1].compras = notas_compiladas[tamanho_notas_compiladas-1].compras + abs(valor)
                elif op == "V":
                    notas_compiladas[tamanho_notas_compiladas-1].vendas = notas_compiladas[tamanho_notas_compiladas-1].vendas + abs(valor)

                operacao = Operacao(data=data_nota, corretora=corretora, ativo=ticker, tipoOp=op, quantidade=quantidade, preco=preco, valor=valor, mercado=mercado, irpf=0.00, taxas=0.00, daytrade=daytrade)
                notas_compiladas[tamanho_notas_compiladas-1].operacoes_compiladas.append(operacao)
                


        else:
            nota_corretagem.texto = nota_corretagem.texto.replace("FRACIONARIO", "VISTA")
            linhas = re.findall(r'1-BOVESPA(.*)\n', nota_corretagem.texto)
            if not linhas:
                linhas = re.findall(r'7-BOVESPA FIX(.*)\n', nota_corretagem.texto)
            if linhas:
                is_opcao = True if re.search(r'OPCAO', linhas[0], re.IGNORECASE) else False
                is_vista = True if re.search(r'VISTA', linhas[0], re.IGNORECASE) else False
                if is_opcao:
                    mercado = "Opções"
                    for linha in linhas:
                        # Operacao
                        op = re.search(r'([VC]) OPCAO', linha, re.IGNORECASE)
                        if op is not None:
                            op = op.group(1)
                        else:
                            raise Exception('Não foi possível identificar se é compra ou venda')

                        # Ticker da Opção
                        ticker = re.search(r'\d{2}/\d{2}.* (\w{5}[0-9]{1,3})\s', linha, re.IGNORECASE)
                        if ticker is not None:
                            ticker = ticker.group(1)
                        else:
                            raise Exception('Não foi possível identificar o ticker da opção')

                        daytrade = True if re.search(r'OPCAO.* [2#8FTI]*D[2#8FTI]* .*-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*', linha, re.IGNORECASE) else False

                        # Grupo de quantidades no fim da linha
                        grupo_quantidades = re.search(r'(-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) [CD]', linha, re.IGNORECASE)
                        if len(grupo_quantidades.groups()) == 9:
                            quantidade = float(grupo_quantidades.group(1).replace('.', '').replace(',', '.'))
                            preco = float(grupo_quantidades.group(4).replace('.', '').replace(',', '.'))
                            valor = float(grupo_quantidades.group(7).replace('.', '').replace(',', '.'))

                            
                            notas_compiladas[tamanho_notas_compiladas-1].volume = notas_compiladas[tamanho_notas_compiladas-1].volume + abs(valor)
                            if op == 'C':
                                notas_compiladas[tamanho_notas_compiladas-1].compras = notas_compiladas[tamanho_notas_compiladas-1].compras + abs(valor)
                            elif op == "V":
                                notas_compiladas[tamanho_notas_compiladas-1].vendas = notas_compiladas[tamanho_notas_compiladas-1].vendas + abs(valor)

                            operacao = Operacao(data=data_nota, corretora=corretora, ativo=ticker, tipoOp=op, quantidade=quantidade, preco=preco, valor=valor, mercado=mercado, irpf=0.00, taxas=0.00, daytrade=daytrade)
                            notas_compiladas[tamanho_notas_compiladas-1].operacoes_compiladas.append(operacao)
                            
                        else:
                            raise Exception('Não foi possível identificar as quantidades da opção')

                elif is_vista:
                    mercado = "A Vista"
                    for linha in linhas:
                        # Operacao
                        op = re.search(r'([VC]) VISTA', linha, re.IGNORECASE)
                        if op is not None:
                            op = op.group(1)
                        else:
                            raise Exception('Não foi possível identificar se é compra ou venda')

                        # Daytrade
                        daytrade = True if re.search(r'VISTA.* [2#8FTI]*D[2#8FTI]* .*-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*', linha, re.IGNORECASE) else False


                        # Ticker do A vista
                        especificacao = re.search(r'VISTA\s(.*\D+\d?)\s\d', linha, re.IGNORECASE)
                        ticker = ""
                        if especificacao is not None:
                            especificacao = especificacao.group(1)
                            especificacao = especificacao.replace("   ", "").rstrip(" ")
                            ticker = find_ticker_by_especificacao(especificacao)
                            if ticker is None:
                                raise Exception('Não foi possível identificar o ticker do ativo a vista')
                        else:
                            raise Exception('Não foi possível identificar a especificação do A vista')

                        # Grupo de quantidades no fim da linha
                        grupo_quantidades = re.search(r'(-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) (-*[0-9]+(\.[0-9]{3})*(,[0-9]+)?-*) [CD]', linha, re.IGNORECASE)
                        if len(grupo_quantidades.groups()) == 9:
                            quantidade = float(grupo_quantidades.group(1).replace('.', '').replace(',', '.'))
                            preco = float(grupo_quantidades.group(4).replace('.', '').replace(',', '.'))
                            valor = float(grupo_quantidades.group(7).replace('.', '').replace(',', '.'))

                            notas_compiladas[tamanho_notas_compiladas-1].volume = notas_compiladas[tamanho_notas_compiladas-1].volume + abs(valor)
                            if op == 'C':
                                notas_compiladas[tamanho_notas_compiladas-1].compras = notas_compiladas[tamanho_notas_compiladas-1].compras + abs(valor)
                            elif op == "V":
                                notas_compiladas[tamanho_notas_compiladas-1].vendas = notas_compiladas[tamanho_notas_compiladas-1].vendas + abs(valor)

                            operacao = Operacao(data=data_nota, corretora=corretora, ativo=ticker, tipoOp=op, quantidade=quantidade, preco=preco, valor=valor, mercado=mercado, irpf=0.00, taxas=0.00, daytrade=daytrade)
                            notas_compiladas[tamanho_notas_compiladas-1].operacoes_compiladas.append(operacao)
                            
                        else:
                            raise Exception('Não foi possível identificar as quantidades da opção')

                else:
                    raise Exception(f'Não foi possível identificar o tipo de operação: {linhas[0]}')
                
                
            else:
                raise Exception("Não foi possível encontrar as operações na nota de corretagem")

    # Calcula as taxas e impostos das operacoes - Impostos apenas atribui para uma operação, sem dividir
    for index_nota_compilada, nota_compilada_item in enumerate(notas_compiladas):
        has_atributed_imposto = False
        if nota_compilada_item.taxas is None:
            notas_compiladas[index_nota_compilada].taxas = nota_compilada_item.vendas - nota_compilada_item.compras - nota_compilada_item.liquido 
        for index_operacao, operacao_item in enumerate(nota_compilada_item.operacoes_compiladas):
            # taxas
            notas_compiladas[index_nota_compilada].operacoes_compiladas[index_operacao].taxas = nota_compilada_item.taxas*operacao_item.valor/nota_compilada_item.volume
            

            # impostos
            # Daytrade IRPF
            if has_atributed_imposto == False:
                if operacao_item.mercado == "BM&F":
                    if operacao_item.tipoOp == "V":
                        notas_compiladas[index_nota_compilada].operacoes_compiladas[index_operacao].irpf = nota_compilada_item.irpf
                        has_atributed_imposto = True


                # Swing Trade, pois Daytrade apenas gera uma projeção que não provisiona
                elif operacao_item.mercado == "A Vista" or operacao_item.mercado == "Opções":
                    if operacao_item.tipoOp == "V":
                        if operacao_item.daytrade == False:
                            notas_compiladas[index_nota_compilada].operacoes_compiladas[index_operacao].irpf = nota_compilada_item.irpf
                            has_atributed_imposto = True

    
    dataframe_operacoes = get_dataframe_from_list_notacompilada(notas_compiladas)
    dataframe_operacoes["datetime"] = dataframe_operacoes["data"].apply(lambda x: datetime.datetime.strptime(x, "%d/%m/%Y"))
    dataframe_operacoes_sorted = dataframe_operacoes.sort_values(['daytrade', 'datetime'], ascending=[False, True])
    dataframe_operacoes_sorted.drop(columns=['datetime'], inplace=True)
    dataframe_operacoes_sorted.to_csv("output/operacoes.csv", index=False)

    # Move all files from folder PASTA_NAO_PROCESSADOS to folder PASTA_PROCESSADOS
    for file in os.listdir(PASTA_NAO_PROCESSADOS):
        shutil.move(os.path.join(PASTA_NAO_PROCESSADOS, file), PASTA_PROCESSADOS)

if __name__ == "__main__":
    setup_folders()
    tratamento_texto_nao_processados()