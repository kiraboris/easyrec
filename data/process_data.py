import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
import os


def generate_sample_data():
    """Generate sample movie recommendation data"""
    np.random.seed(42)
    
    # Generate users
    n_users = 1000
    n_items = 500
    n_ratings = 10000
    
    # User features
    users = pd.DataFrame({
        'user_id': range(1, n_users + 1),
        'gender': np.random.choice([0, 1], n_users),  # 0: Female, 1: Male
        'age': np.random.choice(range(1, 8), n_users),  # Age groups 1-7
        'occupation': np.random.choice(range(21), n_users)  # 21 occupations
    })
    
    # Item features
    genres_list = ['Action', 'Adventure', 'Animation', 'Children', 'Comedy', 
                   'Crime', 'Documentary', 'Drama', 'Fantasy', 'Film-Noir',
                   'Horror', 'Musical', 'Mystery', 'Romance', 'Sci-Fi',
                   'Thriller', 'War', 'Western']
    
    items = pd.DataFrame({
        'item_id': range(1, n_items + 1),
        'genres': [
            '|'.join(np.random.choice(genres_list, 
                                    size=np.random.randint(1, 4), 
                                    replace=False))
            for _ in range(n_items)
        ]
    })
    
    # Generate ratings
    ratings_data = []
    for _ in range(n_ratings):
        user_id = np.random.randint(1, n_users + 1)
        item_id = np.random.randint(1, n_items + 1)
        
        # Simulate some preference patterns
        user_features = users[users['user_id'] == user_id].iloc[0]
        
        # Base rating influenced by user characteristics
        base_rating = 3.0
        if user_features['age'] <= 3:  # Younger users rate higher
            base_rating += 0.5
        if user_features['gender'] == 1:  # Male users slightly different pattern
            base_rating += 0.2
            
        # Add some randomness
        rating = max(1, min(5, base_rating + np.random.normal(0, 1)))
        
        # Convert to binary classification (like/dislike)
        label = 1 if rating >= 4.0 else 0
        
        ratings_data.append({
            'user_id': user_id,
            'item_id': item_id,
            'rating': rating,
            'label': label,
            'timestamp': np.random.randint(946684800, 1609459200)  # 2000-2021
        })
    
    ratings_df = pd.DataFrame(ratings_data)
    
    # Merge with user and item features
    final_data = ratings_df.merge(users, on='user_id').merge(items, on='item_id')
    
    # Shuffle the data
    final_data = final_data.sample(frac=1).reset_index(drop=True)
    
    return final_data


def split_data(data, train_ratio=0.8):
    """Split data into train and test sets"""
    train_size = int(len(data) * train_ratio)
    train_data = data[:train_size]
    test_data = data[train_size:]
    return train_data, test_data


def save_data(data, filepath):
    """Save data to CSV file"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    data.to_csv(filepath, index=False)
    print(f"Data saved to {filepath}, shape: {data.shape}")


def main():
    """Main function to generate and save sample data"""
    print("Generating sample movie recommendation data...")
    
    # Generate data
    data = generate_sample_data()
    
    print(f"Generated {len(data)} ratings")
    print(f"Number of users: {data['user_id'].nunique()}")
    print(f"Number of items: {data['item_id'].nunique()}")
    print(f"Label distribution: {data['label'].value_counts().to_dict()}")
    
    # Split data
    train_data, test_data = split_data(data)
    
    # Save data
    save_data(train_data, 'data/movies_train_data.csv')
    save_data(test_data, 'data/movies_test_data.csv')
    
    # Also save a small sample for quick testing
    sample_data = data.head(100)
    save_data(sample_data, 'data/sample_data.csv')
    
    print("\nData processing completed!")
    print("Files created:")
    print("- data/movies_train_data.csv")
    print("- data/movies_test_data.csv") 
    print("- data/sample_data.csv")


if __name__ == "__main__":
    main()
