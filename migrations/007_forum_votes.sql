-- Forum Votes Table
-- Allows logged-in users to upvote/downvote posts and replies

CREATE TABLE IF NOT EXISTS forum_votes (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    post_id BIGINT NOT NULL REFERENCES forum_posts(id) ON DELETE CASCADE,
    vote_type INT NOT NULL CHECK (vote_type IN (-1, 1)), -- -1 = downvote, 1 = upvote
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, post_id)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_forum_votes_post ON forum_votes(post_id);
CREATE INDEX IF NOT EXISTS idx_forum_votes_user ON forum_votes(user_id);

-- Add vote_count column to forum_posts for quick display
ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS vote_score INT DEFAULT 0;

-- Function to update vote score when votes change
CREATE OR REPLACE FUNCTION update_post_vote_score()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE forum_posts
        SET vote_score = vote_score + NEW.vote_type
        WHERE id = NEW.post_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE forum_posts
        SET vote_score = vote_score - OLD.vote_type
        WHERE id = OLD.post_id;
    ELSIF TG_OP = 'UPDATE' THEN
        -- Vote changed (e.g., from up to down)
        UPDATE forum_posts
        SET vote_score = vote_score - OLD.vote_type + NEW.vote_type
        WHERE id = NEW.post_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update vote scores
DROP TRIGGER IF EXISTS trg_update_vote_score ON forum_votes;
CREATE TRIGGER trg_update_vote_score
AFTER INSERT OR UPDATE OR DELETE ON forum_votes
FOR EACH ROW EXECUTE FUNCTION update_post_vote_score();

-- RLS policies for votes
ALTER TABLE forum_votes ENABLE ROW LEVEL SECURITY;

-- Anyone can read votes
CREATE POLICY "Anyone can view votes" ON forum_votes
    FOR SELECT USING (true);

-- Users can only insert/update/delete their own votes
CREATE POLICY "Users can vote" ON forum_votes
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can change their vote" ON forum_votes
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can remove their vote" ON forum_votes
    FOR DELETE USING (auth.uid() = user_id);
