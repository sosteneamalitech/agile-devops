

# Amalitech Lab 1
Final Assessment – Agile & DevOps in Practice

In this lab I was working on developing a simple ai application that can be used to generate  users stories of given project.


## Github projects



The project focuses on the backend implementation of the project.

I have used Python with FastAPI to implement the project.


# Agile Process
For the  agile board  I have used  github project which can be found below
[Github Project](https://github.com/users/sosteneamalitech/projects/1)
For the sprint planning I have used GitHub internal feature of milestone to be able to impliment the sprint, but for the sake of the implimentation of my feature I have used a sprint of  of 1 days instead of  normal 2 week, and the standup were done for every 2 hours.  and the implimentation of the project was done in 2 days. 

## API

The application exposes two endpoints:

- `GET /users` returns the registered users without passwords.
- `POST /users` registers a user with `name`, `email`, and `password`.
- `POST /login` authenticates a registered user with `email` and `password` and returns an auth token.
- `POST /projects` creates a project with `title` and `description` for the authenticated user.
- `POST /projects/{project_id}/user-stories/generate` generates AI user stories for an authenticated user project.

## Run

Install the project dependencies and start the app with:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Environment Variables

The application needs the following environment variables:

- `JWT_SECRET`
- `JWT_ALGORITHM`
- `AI_API_KEY` for AI story generation
- `AI_BASE_URL` for an OpenAI-compatible API, defaults to `https://api.openai.com/v1`
- `AI_MODEL` optional, defaults to `gpt-4.1-mini`
- `AI_AGENT_MAX_ITERATIONS` optional, defaults to `3`


## Test

Run the test suite with:

```bash
python3 -m pytest
```
### Manual testing
You can use the following curl commands to test the endpoints:
```shell
 curl -X POST "http://127.0.0.1:8000/users" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "your_email@example.com",
       "password": "yourpassword123",
        "name": "Your Name"
     }'
```
login to access the token
```shell
    curl -X POST "http://127.0.0.1:8000/login" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "your_email@example.com",
         "password": "yourpassword123"
        }'
```
you will get a response like this
```json
{
  "token": "your_access_token_here"
  "user_id": 1
}
```

create a project
you can export as variable to use in the next request
```shell
export TOKEN=your_access_token_here
```


```shell
curl -X POST "http://127.0.0.1:8000/projects" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d '{
          "title": "My Project",
          "description": "This is a sample project."
        }'
```
generate user stories for the project generated above, you can export the project_id as variable to use in the next request
```shell 
curl -X POST "http://127.0.0.1:8000/projects/{project_id}/stories" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN"
```



