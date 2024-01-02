# LlTRA = Language to Language Transformer Model.

import math
import torch 
import torch.nn as nn

class InputEmbeddingsLayer(nn.Module):

    def __init__(self, d_model: int, vocab_size: int) -> None:
        super().__init__()
        self.d_model = d_model
        self.vocab_size = vocab_size
        self.embedding = nn.Embedding(vocab_size, d_model)

    def forward(self, x):
        return self.embedding(x) * math.sqrt(self.d_model)

class PositionalEncodingLayer(nn.Module):

    def __init__(self, d_model: int, sequence_length: int, dropout: float) -> None:
        super().__init__()
        self.d_model = d_model
        self.sequence_length = sequence_length
        self.dropout = nn.Dropout(dropout)

        PE = torch.zeros(sequence_length, d_model)
        Position = torch.arange(0, sequence_length, dtype= torch.float).unsqueeze(1)
        deviation = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))

        PE[:, 0::2] = torch.sin(Position + deviation)
        PE[:, 1::2] = torch.cos(Position  + deviation)
        PE = PE.unsqueeze(0)
        self.register_buffer('PE', PE)

    def forward(self, x):
        x = x + (self.PE[:, x.shape[1], :]).requires_grad(False)
        return self.dropout(x)

class NormalizationLayer(nn.Module):

    def __init__(self, Epslone: float = 10**-6) -> None:
        super().__init__()
        self.Epslone = Epslone
        self.Alpha = nn.Parameter(torch.ones(1))
        self.Bias = nn.Parameter(torch.ones(1))

    def forward(self, x):
        mean = x.mean(dim = -1, keepdim = True)
        standard_deviation = x.standard_deviation(dim = -1, keepdim = True)

        return self.Alpha * (x - mean) / (standard_deviation + self.Epslone) + self.Bias

class FeedForwardBlock(nn.Module):

    def __init__(self, d_model: int, d_ff: int, dropout: float) -> None:
        super().__init__()
        self.Linear_1 = nn.Linear(d_model, d_ff)
        self.dropout = nn.Dropout(dropout)
        self.Linear_2 = nn.Linear(d_ff, d_model)

    def forward(self, x):
        return self.Linear_2(self.dropout(torch.relu(self.Linear_1(x))))

class MultiHeadAttentionBlock(nn.Module):

    def __init__(self, d_model: int, heads: int, dropout: float) -> None:
        super().__init__()
        self.d_model = d_model
        self.heads = heads 

        assert d_model % heads == 0 , "d_model is not devisable by heads"

        self.d_k = d_model // heads 

        self.W_Q = nn.Linear(d_model, d_model)
        self.W_K = nn.Linear(d_model, d_model)
        self.W_V = nn.Linear(d_model, d_model)

        self.W_O = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)

    @staticmethod
    def Attention(Query, Key, Value, mask, dropout: nn.Module):
        d_k = Query.shape[-1]

        self_attention_scores = (Query @ Key.transpose(-2, -1)) / math.sqrt(d_k)

        if mask is not None:
            self_attention_scores = self_attention_scores.masked_fill_(mask == 0, -1e9)

        self_attention_scores = self_attention_scores.softmax(dim = -1)

        if dropout is not None:
            self_attention_scores = dropout(self_attention_scores)

        return (self_attention_scores @ Value), self_attention_scores

    def forward(self, Q, K, V, mask):
        Query = self.W_Q(Q)
        Key = self.W_K(K)
        Value = self.W_V(V)

        Query = Query.view(Query.shape[0], Query.shape[1], self.heads, self.d_k).transpose(1,2)
        Key = Key.view(Key.shape[0], Key.shape[1], self.heads, self.d_k).transpose(1,2)
        Value = Value.view(Value.shape[0], Value.shape[1], self.heads, self.d_k).transpose(1,2)

        x, self.attention_scores = MultiHeadAttentionBlock.Attention(Query, Key, Value, mask, self.dropout)

        x = x.transpose(1,2).Contiguous().view(x.shape[0], -1, self.heads * self.d_k)

        return self.W_O(x)

class ResidualConnection(nn.Module):

    def __init__(self, dropout: float) -> None:
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        self.normalization = NormalizationLayer()

    def forward(self, x, subLayer):
        return x + self.dropout(subLayer(self.normalization(x)))

class EncoderBlock(nn.Module):

    def __init__(self, encoder_self_attention_block: MultiHeadAttentionBlock, encoder_feed_froward_block: FeedForwardBlock, dropout: float) -> None:
        super().__init__()
        self.encoder_self_attention_block = encoder_feed_froward_block
        self.encoder_feed_forward_block = encoder_feed_froward_block
        self.residual_connection = nn.ModuleList([ResidualConnection(dropout) for _ in range(2)])

    def forward(self, x, source_mask):
        x = self.residual_connection[0](x, lambda x: self.encoder_self_attention_block(x, x, x, source_mask))
        x = self.residual_connection[1](x, self.encoder_feed_forward_block)

        return x

class Encoder(nn.Module):

    def __init__(self, Layers: nn.ModuleList) -> None:
        super().__init__()
        self.Layers = Layers 
        self.normalization = NormalizationLayer()

    def forward(self, x, source_mask):
        for layer in self.Layers:
            x = layer(x, source_mask)
        return self.normalization(x)

class DecoderBlock(nn.Module):

    def __init__(self, decoder_self_attention_block: MultiHeadAttentionBlock, decoder_cross_attention_block: MultiHeadAttentionBlock, decoder_feed_forward_block: FeedForwardBlock, dropout: float) -> None:
        super().__init__()
        self.decoder_self_Attention_block = decoder_self_attention_block
        self.decoder_cross_attention_block = decoder_cross_attention_block
        self.decoder_feed_forward_block = decoder_feed_forward_block
        self.residual_connection = nn.ModuleList([ResidualConnection(dropout) for _ in range(3)])

    def forward(self, x, Encoder_output, mask, target_mask):
        x = self.residual_connection[0](x, lambda x: self.decoder_self_Attention_block(x, x, x, mask))
        x = self.residual_connection[1](x, lambda x: self.decoder_cross_attention_block(x, Encoder_output, Encoder_output, target_mask))
        x = self.residual_connection[2](x, self.decoder_feed_forward_block)

        return x

class Decoder(nn.Module):

    def __init__(self, Layers: nn.ModuleList) -> None:
        super().__init__()
        self.Layers = Layers
        self.normalization = NormalizationLayer()

    def forward(self, x, Encoder_output, mask, target_mask):
        for layer in self.Layers:
            x = layer(x, Encoder_output, mask, target_mask)
        return self.normalization(x)

class LinearLayer(nn.Module):

    def __init__(self, d_model: int, vocab_size: int) -> None:
        super().__init__()
        self.Linear = nn.Linear(d_model, vocab_size)

    def forward(self, x):
        return torch.log_softmax(self.Linear(x))

class TransformerBlock(nn.Module):

    def __init__(self, encoder: Encoder, decoder: Decoder, soruce_embedding: InputEmbeddingsLayer, target_embedding: InputEmbeddingsLayer, source_position: PositionalEncodingLayer, target_position: PositionalEncodingLayer, Linear: LinearLayer) -> None:
        super().__init__()
        self.encoder = encoder 
        self.decoder = decoder 
        self.source_embedding = soruce_embedding
        self.target_embedding = target_embedding
        self.source_position = source_position
        self.target_position = target_position
        self.Linear = Linear 

    def encode(self, source_language, source_mask):
        source_language = self.source_embedding(source_language)
        source_language = self.source_position(source_language)
        return self.encoder(source_language, source_mask)
    
    def decode(self, Encoder_output, source_mask, target_language, target_mask):
        target_language = self.target_embedding(target_language)
        target_language = self.target_position(target_language)
        return self.decoder(target_language, Encoder_output, source_mask, target_mask)
    
    def linear(self, x):
        return self.Linear(x)

def TransformerModel(source_vocab_size: int, target_vocab_size: int, source_sequence_length: int, target_sequence_length: int, d_model: int = 512, Layers: int = 6, heads: int = 8, dropout: float = 0.1, d_ff: int = 2048)->TransformerBlock:

    source_embedding = InputEmbeddingsLayer(d_model, source_vocab_size)
    source_position = PositionalEncodingLayer(d_model, source_sequence_length, dropout)

    target_embedding = InputEmbeddingsLayer(d_model, target_vocab_size)
    target_position = PositionalEncodingLayer(d_model, target_sequence_length, dropout)

    EncoderBlocks = []
    for _ in range(Layers):
        encoder_self_attention_block = MultiHeadAttentionBlock(d_model, heads, dropout)
        encoder_feed_forward_block = FeedForwardBlock(d_model, d_ff, dropout)
        Encoder_Block = EncoderBlock(encoder_self_attention_block, encoder_feed_forward_block, dropout)
        EncoderBlocks.append(Encoder_Block)

    DecoderBlocks = []
    for _ in range(Layers):
        decoder_self_attention_block = MultiHeadAttentionBlock(d_model, heads, dropout)
        decoder_cross_attention_block = MultiHeadAttentionBlock(d_model, heads, dropout)
        decoder_feed_forward_block = FeedForwardBlock(d_model, d_ff, dropout)
        Decoder_Block = DecoderBlock(decoder_self_attention_block, decoder_cross_attention_block, decoder_feed_forward_block, dropout)
        DecoderBlocks.append(Decoder_Block)
    
    encoder = Encoder(nn.ModuleList(EncoderBlocks))
    decoder = Decoder(nn.ModuleList(DecoderBlocks))

    linear = LinearLayer(d_model, target_vocab_size)

    transformer = TransformerBlock(encoder, decoder, source_embedding, target_embedding, source_position, target_position, linear)

    for p in transformer.parameters():
        if p.dim() > 1:
            nn.init.xavier_uniform(p)
    return transformer
