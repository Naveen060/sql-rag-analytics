import hashlib
import json
import os
import faiss
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

class SchemaRetriever:
    def __init__(self, schema):
        self.schema = schema
        self.names = list(schema)
        self.texts = [f'{n}: {schema[n]["description"]}. Columns: {schema[n]["columns"]}' for n in self.names]
        self.semantic = os.getenv('EMBEDDING_BACKEND', 'hash') == 'sentence-transformers'
        if self.semantic:
            from sentence_transformers import SentenceTransformer
            self.encoder = SentenceTransformer(os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'))
        else:
            self.encoder = HashingVectorizer(n_features=384, alternate_sign=False, norm='l2')
        vectors = self.embed(self.texts)
        self.remote = os.getenv('VECTOR_BACKEND', 'faiss') == 'pinecone'
        if self.remote:
            from pinecone import Pinecone
            self.index = Pinecone(api_key=os.environ['PINECONE_API_KEY']).Index(host=os.environ['PINECONE_INDEX_HOST'])
            # Schema + encoder fingerprint avoids mixing stale catalogs and embedding spaces.
            fingerprint = json.dumps(schema, sort_keys=True) + str(self.semantic) + os.getenv('EMBEDDING_MODEL', '')
            self.namespace = 'schema-' + hashlib.sha256(fingerprint.encode()).hexdigest()[:20]
            self.index.upsert(namespace=self.namespace, vectors=[
                {'id':name, 'values':v.tolist()} for name,v in zip(self.names, vectors)])
        else:
            self.index = faiss.IndexFlatIP(vectors.shape[1])
            self.index.add(vectors)

    def embed(self, texts):
        if self.semantic:
            return np.asarray(self.encoder.encode(texts, normalize_embeddings=True), dtype='float32')
        return self.encoder.transform(texts).toarray().astype('float32')

    def search(self, question, k=4):
        vector = self.embed([question])
        if self.remote:
            matches = self.index.query(namespace=self.namespace, vector=vector[0].tolist(), top_k=min(k,len(self.names)))
            names = [m.id for m in matches.matches if m.id in self.schema]
        else:
            _, ids = self.index.search(vector, min(k, len(self.names)))
            names = [self.names[i] for i in ids[0] if i >= 0]
        return {n:self.schema[n] for n in names}
