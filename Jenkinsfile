#!groovy
import groovy.json.JsonOutput
import groovy.json.JsonSlurper

pipeline {
    agent {
      label 'av'
    }

    environment {
      GITHUB_TOKEN = credentials('av-github-token')
    }
    stages {
        stage('Notify Github about pending job') {
            steps {
                notifyGithub("pending", "The build has started..")
            }
        }
        stage('Run ansible') {
            steps {
                echo 'Running ansible...'
                script {
                  currentBuild.result = 'success'
                }
            }
        }
        stage('Notify Github about finished job') {
            steps {
              script {
                def build_status = currentBuild.result
                def status
                if ( build_status == 'SUCCESS' ){
                  notifyGithub('success', 'The build succeeded!' )
                }
                else {
                  notifyGithub('failure', 'The build failed :(')
                }
              }
            }
        }
    }
}


def notifyGithub(state, description){
  def githubURL = "https://api.github.com/repos/vrk-kpa/opendata/statuses/$GIT_COMMIT?access_token=$GITHUB_TOKEN"
  def payload = JsonOutput.toJson([
    state: state,
    description: description,
    target_url: "https://vrk-jenkins.eden.csc.fi/job/av/job/av-pipeline/job/$BRANCH_NAME/$BUILD_NUMBER/console",
    context: "continuous-integration/jenkins"
  ])

  sh "curl -X POST -H 'Content-Type: application/json' -d \'${payload}\' ${githubURL}"
}
