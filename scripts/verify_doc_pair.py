from weaviate.classes.query import Filter
from src.weaviate.client import get_weaviate_client

def check_adr(n: str):
    client = get_weaviate_client()
    try:
        c = client.collections.get("ArchitecturalDecision")
        res = c.query.fetch_objects(
            filters=Filter.by_property("adr_number").equal(n),
            return_properties=["file_path", "title", "doc_type", "adr_number"],
            limit=50,
        )
        print(f"\nADR {n} objects:")
        for o in res.objects:
            p = o.properties
            print(p.get("doc_type"), "|", p.get("adr_number"), "|", p.get("title"), "|", p.get("file_path"))
    finally:
        client.close()

def check_pcp(n: str):
    client = get_weaviate_client()
    try:
        c = client.collections.get("Principle")
        res = c.query.fetch_objects(
            filters=Filter.by_property("principle_number").equal(n),
            return_properties=["file_path", "title", "doc_type", "principle_number"],
            limit=50,
        )
        print(f"\nPCP {n} objects:")
        for o in res.objects:
            p = o.properties
            print(p.get("doc_type"), "|", p.get("principle_number"), "|", p.get("title"), "|", p.get("file_path"))
    finally:
        client.close()

if __name__ == "__main__":
    check_adr("0025")
    check_pcp("0010")
