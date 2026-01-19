"""Test script to verify Ollama embedding model is working."""

import asyncio


async def test_ollama():
    """Test Ollama embedding provider."""
    from freshroles.matching.embeddings.ollama import OllamaEmbeddingProvider
    
    print("=" * 50)
    print("Ollama Embedding Test")
    print("=" * 50)
    
    provider = OllamaEmbeddingProvider(model="nomic-embed-text")
    
    # Check if Ollama server is running
    print("\n1. Checking Ollama server...")
    available = await provider.is_available()
    
    if not available:
        print("   ❌ Ollama is not running or model not found")
        print("\n   To fix this:")
        print("   1. Install Ollama: https://ollama.ai")
        print("   2. Start Ollama")
        print("   3. Run: ollama pull nomic-embed-text")
        return False
    
    print("   ✅ Ollama server is running")
    print("   ✅ nomic-embed-text model available")
    
    # Test embedding generation
    print("\n2. Testing embedding generation...")
    test_texts = [
        "Software Engineer Intern looking for Python and backend development",
        "Senior Staff Engineer with 10+ years experience",
    ]
    
    try:
        embeddings = await provider.embed(test_texts)
        
        print(f"   ✅ Generated {len(embeddings)} embeddings")
        print(f"   ✅ Embedding dimension: {len(embeddings[0])}")
        
        # Test similarity
        print("\n3. Testing similarity computation...")
        sim = provider.similarity(embeddings[0], embeddings[1])
        print(f"   ✅ Similarity between test texts: {sim:.4f}")
        
        # These texts should be somewhat different
        if sim < 0.9:
            print("   ✅ Similarity score looks reasonable")
        
        print("\n" + "=" * 50)
        print("All tests passed! Ollama is working correctly. 🎉")
        print("=" * 50)
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(test_ollama())
